import os
import shutil
import subprocess
import time
from pathlib import Path

import httpx
import pytest


TESTS_DIR = Path(__file__).resolve().parents[1]
COMPOSE_FILE = TESTS_DIR / "docker-compose.yaml"
COMPOSE_PROJECT_NAME = "tks-essentials-test-int-kafka-cluster"
BOOTSTRAP_BROKERS = "localhost:9092,localhost:9093,localhost:9094"
KSQLDB_URL = "http://localhost:8088"
LEGACY_TEST_CONTAINERS = ("kafka1", "kafka2", "kafka3", "ksqldb-server")


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


def _compose_args(compose_cmd: list[str]) -> list[str]:
    return compose_cmd + ["-p", COMPOSE_PROJECT_NAME, "-f", str(COMPOSE_FILE)]


def _wait_for_kafka(compose_cmd: list[str], timeout_s: int = 180) -> None:
    deadline = time.monotonic() + timeout_s
    command = _compose_args(compose_cmd) + [
        "exec",
        "-T",
        "kafka1",
        "kafka-topics",
        "--bootstrap-server",
        "kafka1:29092",
        "--list",
    ]

    while time.monotonic() < deadline:
        result = _run(command, check=False)
        if result.returncode == 0:
            return
        time.sleep(2)

    raise RuntimeError("Kafka cluster did not become ready in time.")


def _wait_for_ksqldb(timeout_s: int = 180) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{KSQLDB_URL}/info", timeout=5.0)
            if response.status_code == 200:
                info = response.json()
                if info.get("KsqlServerInfo", {}).get("serverStatus") == "RUNNING":
                    return
        except httpx.HTTPError:
            pass
        time.sleep(2)

    raise RuntimeError("ksqlDB did not become ready in time.")


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
    compose_cmd = _compose_command()

    os.environ["ENV"] = "DEV"
    os.environ["KAFKA_BROKER_STRING"] = BOOTSTRAP_BROKERS
    os.environ["KSQLDB_STRING"] = KSQLDB_URL

    _remove_legacy_test_containers()
    _run(_compose_args(compose_cmd) + ["up", "-d", "--remove-orphans"])
    try:
        _wait_for_kafka(compose_cmd)
        _wait_for_ksqldb()
        yield
    finally:
        _run(
            _compose_args(compose_cmd) + ["down", "-v", "--remove-orphans"],
            check=False,
        )
