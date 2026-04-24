import importlib.util
from pathlib import Path
import subprocess
import uuid

import pytest


def _load_int_conftest():
    module_path = Path(__file__).resolve().parent / "int" / "conftest.py"
    module_name = f"int_conftest_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_compose_file_selection_prefers_env_override(monkeypatch, tmp_path):
    int_conftest = _load_int_conftest()

    override_file = tmp_path / "override-compose.yaml"
    override_file.write_text("version: '3'")
    classic_file = tmp_path / "classic-compose.yaml"
    classic_file.write_text("version: '3'")

    monkeypatch.setenv("TKS_KAFKA_COMPOSE_FILE", str(override_file))
    monkeypatch.setattr(int_conftest, "CLASSIC_COMPOSE_FILE", classic_file)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    assert int_conftest._resolve_compose_file() == override_file


def test_relative_override_is_resolved_against_repo_root(monkeypatch, tmp_path):
    int_conftest = _load_int_conftest()

    relative_override = Path("local") / "docker-compose.yaml"
    resolved_override = tmp_path / relative_override
    resolved_override.parent.mkdir(parents=True, exist_ok=True)
    resolved_override.write_text("version: '3'")

    monkeypatch.setattr(int_conftest, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(int_conftest, "CLASSIC_COMPOSE_FILE", tmp_path / "classic-compose.yaml")
    monkeypatch.setenv("TKS_KAFKA_COMPOSE_FILE", str(relative_override))
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    assert int_conftest._resolve_compose_file() == resolved_override


def test_compose_file_selection_ci_prefers_local_stack(monkeypatch, tmp_path):
    int_conftest = _load_int_conftest()

    local_compose = tmp_path / "tests" / "docker-compose.yaml"
    local_compose.parent.mkdir(parents=True, exist_ok=True)
    local_compose.write_text("version: '3'")
    classic_file = tmp_path / "classic-compose.yaml"
    classic_file.write_text("version: '3'")

    monkeypatch.setenv("CI", "true")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("TKS_KAFKA_COMPOSE_FILE", raising=False)
    monkeypatch.setattr(int_conftest, "COMPOSE_FILE", local_compose)
    monkeypatch.setattr(int_conftest, "CLASSIC_COMPOSE_FILE", classic_file)

    assert int_conftest._resolve_compose_file() == local_compose


def test_compose_file_selection_falls_back_to_classic(monkeypatch, tmp_path):
    int_conftest = _load_int_conftest()

    classic_file = tmp_path / "classic-compose.yaml"
    classic_file.write_text("version: '3'")

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("TKS_KAFKA_COMPOSE_FILE", raising=False)
    monkeypatch.setattr(int_conftest, "CLASSIC_COMPOSE_FILE", classic_file)

    assert int_conftest._resolve_compose_file() == classic_file


def test_compose_file_selection_fails_with_actionable_error(monkeypatch, tmp_path):
    int_conftest = _load_int_conftest()

    missing_local = tmp_path / "tests" / "docker-compose.yaml"
    missing_classic = tmp_path / "classic-compose.yaml"
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("TKS_KAFKA_COMPOSE_FILE", raising=False)
    monkeypatch.setattr(int_conftest, "COMPOSE_FILE", missing_local)
    monkeypatch.setattr(int_conftest, "CLASSIC_COMPOSE_FILE", missing_classic)

    with pytest.raises(RuntimeError) as exc:
        int_conftest._resolve_compose_file()

    assert "Set TKS_KAFKA_COMPOSE_FILE" in str(exc.value)


def test_prepare_stack_reuses_running_services_without_start(monkeypatch):
    int_conftest = _load_int_conftest()

    monkeypatch.setattr(int_conftest, "_services_ready", lambda: True)
    monkeypatch.setattr(int_conftest, "_resolve_compose_file", lambda: (_ for _ in ()).throw(AssertionError("should not resolve")))
    monkeypatch.setattr(int_conftest, "_run", lambda *args, **kwargs: None)

    started_stack, compose_file = int_conftest._prepare_integration_stack(["docker", "compose"])

    assert started_stack is False
    assert compose_file is None


def test_finalize_integration_stack_skips_teardown_when_not_started(monkeypatch):
    int_conftest = _load_int_conftest()
    executed_commands: list[tuple[list[str], bool]] = []

    def fake_run(command, check=True):
        executed_commands.append((command, check))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(int_conftest, "_run", fake_run)

    int_conftest._finalize_integration_stack(False, ["docker", "compose"], None)

    assert not any(("down" in command for command, _ in executed_commands))


def test_finalize_integration_stack_runs_down_when_stack_started(monkeypatch, tmp_path):
    int_conftest = _load_int_conftest()
    compose_file = tmp_path / "compose.yaml"
    compose_file.write_text("version: '3'")
    executed_commands: list[tuple[list[str], bool]] = []

    def fake_run(command, check=True):
        executed_commands.append((command, check))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(int_conftest, "_run", fake_run)

    int_conftest._finalize_integration_stack(True, ["docker", "compose"], compose_file)

    assert executed_commands
    command, check = executed_commands[0]
    assert command[-3:] == ["down", "-v", "--remove-orphans"]
    assert check is False
