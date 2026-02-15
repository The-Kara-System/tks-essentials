import inspect
import logging
from types import SimpleNamespace
from unittest.mock import Mock

from tksessentials import global_logger, utils


class _NoOpQueueListener:
    def __init__(self, *args, **kwargs):
        self.handlers = args[1:]

    def start(self):
        return None


def _build_test_logger(name):
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.propagate = False
    return logger


def test_setup_custom_logger_returns_cached_instance():
    global_logger.loggers.clear()
    cached_logger = object()
    global_logger.loggers["cached-logger"] = cached_logger

    assert global_logger.setup_custom_logger("cached-logger") is cached_logger


def test_setup_custom_logger_returns_existing_logger_with_handlers(monkeypatch):
    logger_name = "existing-logger-with-handlers"
    test_logger = _build_test_logger(logger_name)

    monkeypatch.setattr(test_logger, "hasHandlers", lambda: True)
    monkeypatch.setattr(logging, "getLogger", lambda name=None: test_logger)
    global_logger.loggers.clear()

    assert global_logger.setup_custom_logger(logger_name) is test_logger


def test_setup_custom_logger_handles_stdout_reconfigure_exception(monkeypatch):
    class BrokenStream:
        def reconfigure(self, **kwargs):
            raise RuntimeError("cannot reconfigure")

        def write(self, *_):
            return None

        def flush(self):
            return None

    logger_name = "logger-reconfigure-exception"
    test_logger = _build_test_logger(logger_name)
    original_get_logger = logging.getLogger

    monkeypatch.setattr(global_logger.sys, "stdout", BrokenStream())
    monkeypatch.setattr(global_logger.sys, "stderr", BrokenStream())
    monkeypatch.setenv("ENV", "PROD")
    monkeypatch.setattr(utils, "get_logging_level", lambda: "INFO")
    monkeypatch.setattr(inspect, "stack", lambda: [])
    monkeypatch.setattr(logging.handlers, "QueueListener", _NoOpQueueListener)
    monkeypatch.setattr(test_logger, "hasHandlers", lambda: False)
    monkeypatch.setattr(
        logging,
        "getLogger",
        lambda name=None: test_logger if name == logger_name else original_get_logger(name),
    )
    global_logger.loggers.clear()

    assert global_logger.setup_custom_logger(logger_name) is test_logger


def test_setup_custom_logger_handles_file_handler_failure(monkeypatch):
    class StreamWithReconfigure:
        def reconfigure(self, **kwargs):
            return None

        def write(self, *_):
            return None

        def flush(self):
            return None

    logger_name = "logger-file-handler-failure"
    test_logger = _build_test_logger(logger_name)
    original_get_logger = logging.getLogger

    monkeypatch.setattr(global_logger.sys, "stdout", StreamWithReconfigure())
    monkeypatch.setattr(global_logger.sys, "stderr", StreamWithReconfigure())
    monkeypatch.setenv("ENV", "DEV")
    monkeypatch.setattr(utils, "get_logging_level", lambda: "INFO")
    monkeypatch.setattr(utils, "get_log_path", Mock(side_effect=OSError("cannot create logs")))
    monkeypatch.setattr(inspect, "stack", lambda: [])
    monkeypatch.setattr(logging.handlers, "QueueListener", _NoOpQueueListener)
    monkeypatch.setattr(test_logger, "hasHandlers", lambda: False)
    monkeypatch.setattr(
        logging,
        "getLogger",
        lambda name=None: test_logger if name == logger_name else original_get_logger(name),
    )
    global_logger.loggers.clear()

    assert global_logger.setup_custom_logger(logger_name) is test_logger


def test_setup_custom_logger_logs_startup_settings_for_main(monkeypatch):
    class StreamWithReconfigure:
        def reconfigure(self, **kwargs):
            return None

        def write(self, *_):
            return None

        def flush(self):
            return None

    logger_name = "logger-main-stack"
    test_logger = _build_test_logger(logger_name)
    original_get_logger = logging.getLogger
    info_spy = Mock()

    monkeypatch.setattr(global_logger.sys, "stdout", StreamWithReconfigure())
    monkeypatch.setattr(global_logger.sys, "stderr", StreamWithReconfigure())
    monkeypatch.setenv("ENV", "PROD")
    monkeypatch.setattr(utils, "get_logging_level", lambda: "INFO")
    monkeypatch.setattr(utils, "get_application_name", lambda: "app-name")
    monkeypatch.setattr(utils, "get_environment", lambda: "DEV")
    monkeypatch.setattr(utils, "get_domain_name", lambda: "domain-name")
    monkeypatch.setattr(utils, "get_project_root", lambda: "c:/project")
    monkeypatch.setattr(utils, "get_log_path", lambda: "c:/project/logs")
    monkeypatch.setattr(inspect, "stack", lambda: [SimpleNamespace(filename="c:/project/main.py")])
    monkeypatch.setattr(logging.handlers, "QueueListener", _NoOpQueueListener)
    monkeypatch.setattr(test_logger, "hasHandlers", lambda: False)
    monkeypatch.setattr(test_logger, "info", info_spy)
    monkeypatch.setattr(
        logging,
        "getLogger",
        lambda name=None: test_logger if name == logger_name else original_get_logger(name),
    )
    global_logger.loggers.clear()

    logger = global_logger.setup_custom_logger(logger_name)

    assert logger is test_logger
    assert info_spy.call_count == 5
