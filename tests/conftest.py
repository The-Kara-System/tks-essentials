import os
import tempfile
from pathlib import Path


PROJECT_ROOT = os.environ.get("PROJECT_ROOT")
if PROJECT_ROOT is None:
    temp_root = Path(tempfile.mkdtemp(prefix="tksessentials_tests_"))
    os.environ["PROJECT_ROOT"] = str(temp_root)
else:
    temp_root = Path(PROJECT_ROOT)

temp_root = Path(os.environ["PROJECT_ROOT"])
(temp_root / "config").mkdir(parents=True, exist_ok=True)
(temp_root / "logs").mkdir(parents=True, exist_ok=True)
app_config_path = temp_root / "config" / "app_config.yaml"
if not app_config_path.exists():
    app_config_path.write_text(
        "application: tks_essentials_test\n"
        "domain: tks/testing\n"
        "developer: Codex\n"
        "logging_level: DEBUG\n",
        encoding="utf-8",
    )


def _integration_tests_requested(args: list[str]) -> bool:
    for arg in args:
        normalized = str(arg).replace("\\", "/").rstrip("/")
        if (
            normalized == "tests/int"
            or normalized.startswith("tests/int/")
            or normalized.endswith("/tests/int")
            or "/tests/int/" in normalized
        ):
            return True
    return False


def pytest_ignore_collect(collection_path: Path, config) -> bool:
    normalized = str(collection_path).replace("\\", "/")
    is_integration_path = normalized.endswith("/tests/int") or "/tests/int/" in normalized
    if not is_integration_path:
        return False

    return not _integration_tests_requested(config.args)
