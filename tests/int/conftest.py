import os
import asyncio
import shutil
import subprocess
import time
from collections.abc import Iterable
from pathlib import Path

import pytest
from aiokafka.admin import AIOKafkaAdminClient

from tksessentials import database


TESTS_DIR = Path(__file__).resolve().parents[1]
COMPOSE_FILE = TESTS_DIR / "docker-compose.yaml"
REPO_ROOT = TESTS_DIR.parent
CLASSIC_COMPOSE_FILE = (
    REPO_ROOT / ".." / ".." / "FA" / "fa-kafka-cluster-dev" / "docker-compose.yaml"
)
COMPOSE_PROJECT_NAME = "tks-essentials-test-int-kafka-cluster"
BOOTSTRAP_BROKERS = "localhost:9092,localhost:9093,localhost:9094"
KSQLDB_URL = "http://localhost:8088"
LEGACY_TEST_CONTAINERS = ("kafka1", "kafka2", "kafka3", "ksqldb-server")
REQUIRED_KAFKA_BROKERS = 3


def _compose_command() -> list[str]:
    docker_compose = shutil.which("docker-compose")
    if docker_compose:
        return [docker_compose]

    docker = shutil.which("docker")
    if docker:
        result = subprocess.run(
            [docker, "compose", "version"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return [docker, "compose"]

    raise RuntimeError("Docker Compose is required to run integration tests.")


def _is_ci_environment() -> bool:
    ci_value = os.getenv("CI", "").strip().lower()
    gha_value = os.getenv("GITHUB_ACTIONS", "").strip().lower()
    return ci_value in {"1", "true", "yes", "on"} or gha_value in {"1", "true", "yes", "on"}


def _normalize_compose_file(path_value: str | Path) -> Path:
    compose_path = Path(path_value)
    if not compose_path.is_absolute():
        compose_path = REPO_ROOT / compose_path
    return compose_path.resolve()


def _compose_file_candidates() -> list[tuple[str, Path]]:
    candidates: list[tuple[str, Path]] = []
    override = os.getenv("TKS_KAFKA_COMPOSE_FILE")
    if override:
        candidates.append(("TKS_KAFKA_COMPOSE_FILE", _normalize_compose_file(override)))
    if _is_ci_environment():
        candidates.append(("CI local fallback", COMPOSE_FILE.resolve()))
    candidates.append(("classic peer fallback", CLASSIC_COMPOSE_FILE.resolve()))
    return candidates


def _resolve_compose_file() -> Path:
    for _, compose_file in _compose_file_candidates():
        if compose_file.is_file():
            return compose_file
    raise RuntimeError(
        "No running Kafka/ksqlDB found and no compose file available. "
        "Set TKS_KAFKA_COMPOSE_FILE to a valid compose file or start required services externally."
    )


def _run(command: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=TESTS_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def _compose_args(compose_cmd: list[str], compose_file: Path) -> list[str]:
    return compose_cmd + ["-p", COMPOSE_PROJECT_NAME, "-f", str(compose_file)]


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    event_loop = asyncio.new_event_loop()
    try:
        return event_loop.run_until_complete(coro)
    finally:
        event_loop.close()


async def _get_kafka_broker_count() -> int:
    admin = AIOKafkaAdminClient(bootstrap_servers=BOOTSTRAP_BROKERS.split(","))
    await admin.start()
    try:
        metadata = await admin.describe_cluster()
    finally:
        await admin.close()

    brokers = getattr(metadata, "brokers", None)
    if isinstance(brokers, Iterable) and not isinstance(metadata, str):
        return len(list(brokers))

    if isinstance(metadata, dict):
        metadata_brokers = metadata.get("brokers")
        if isinstance(metadata_brokers, Iterable):
            return len(list(metadata_brokers))

    raise TypeError("Unexpected kafka cluster metadata shape when counting brokers.")


def _services_readiness() -> tuple[bool, bool, int, str]:
    details = []

    try:
        kafka_ready = _run_async(database.is_kafka_available())
    except Exception:
        details.append("Kafka not available from client probe.")
        kafka_ready = False

    if not kafka_ready:
        details.append("Waiting for Kafka bootstrap brokers.")

    try:
        ksqldb_ready = bool(database.is_ksqldb_available())
    except Exception:
        details.append("ksqlDB probe failed.")
        ksqldb_ready = False

    try:
        broker_count = _run_async(_get_kafka_broker_count())
    except Exception:
        details.append("Kafka cluster metadata not yet ready.")
        broker_count = 0


    details.append(f"Kafka broker count currently {broker_count}.")

    ready = bool(
        kafka_ready
        and ksqldb_ready
        and broker_count >= REQUIRED_KAFKA_BROKERS
    )

    if not ready and ksqldb_ready and kafka_ready:
        details.append(
            f"Expected at least {REQUIRED_KAFKA_BROKERS} brokers before proceeding."
        )

    return ready, bool(kafka_ready), broker_count, ", ".join(details)


def _services_ready() -> bool:
    return _services_readiness()[0]


def _wait_for_services(timeout_s: int = 300, poll_s: float = 2.0) -> None:
    if timeout_s <= 0:
        raise RuntimeError("Integration wait timeout must be greater than zero.")

    deadline = time.monotonic() + timeout_s
    attempts = 0
    last_detail = "not started"
    while time.monotonic() < deadline:
        attempts += 1
        ready, _, _, detail = _services_readiness()
        if ready:
            print(f"Kafka and ksqlDB are reachable and stable after {attempts} checks.")
            return
        last_detail = detail
        print(f"Waiting for services (attempt {attempts}): {detail}")
        time.sleep(poll_s)

    raise RuntimeError(
        f"Kafka and/or ksqlDB did not become ready in time. "
        f"Last check: {last_detail}"
    )


def _prepare_integration_stack(compose_cmd: list[str]) -> tuple[bool, Path | None]:
    if _services_ready():
        print("Precheck passed: using existing Kafka stack.")
        return False, None

    ready, _, _, detail = _services_readiness()
    if ready:
        print("Precheck passed: services became ready during detailed check.")
        return False, None
    print(f"Precheck details before starting compose: {detail}")

    compose_file = _resolve_compose_file()
    print(f"Precheck failed: starting integration services from {compose_file}.")

    _remove_legacy_test_containers()
    _run(_compose_args(compose_cmd, compose_file) + ["up", "-d", "--remove-orphans"])
    _wait_for_services()

    return True, compose_file


def _finalize_integration_stack(
    started_stack: bool,
    compose_cmd: list[str],
    compose_file: Path | None,
) -> None:
    if not started_stack:
        return

    _run(
        _compose_args(compose_cmd, compose_file) + ["down", "-v", "--remove-orphans"],
        check=False,
    )


def _remove_legacy_test_containers() -> None:
    docker = shutil.which("docker")
    if not docker:
        return

    for container in LEGACY_TEST_CONTAINERS:
        subprocess.run(
            [docker, "rm", "-f", container],
            cwd=TESTS_DIR,
            capture_output=True,
            text=True,
            check=False,
        )


@pytest.fixture(scope="session", autouse=True)
def integration_stack():
    try:
        compose_cmd = _compose_command()
    except RuntimeError as exc:
        pytest.skip(
            f"Integration tests require Docker Compose for Kafka/ksqlDB stack: {exc}"
        )

    os.environ["ENV"] = "DEV"
    os.environ["KAFKA_BROKER_STRING"] = BOOTSTRAP_BROKERS
    os.environ["KSQLDB_STRING"] = KSQLDB_URL

    try:
        started_stack, compose_file = _prepare_integration_stack(compose_cmd)
    except RuntimeError as exc:
        pytest.skip(
            f"Integration stack could not be prepared in this environment: {exc}"
        )

    try:
        yield
    finally:
        _finalize_integration_stack(started_stack, compose_cmd, compose_file)
