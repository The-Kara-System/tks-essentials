import inspect
import logging

from tksessentials import global_logger, utils


class _NoOpQueueListener:
    def __init__(self, *args, **kwargs):
        self.handlers = args[1:]

    def start(self):
        return None


def test_setup_custom_logger_creates_log_dir(tmp_path, monkeypatch):
    log_path = tmp_path / "logs"

    monkeypatch.setattr(utils, "get_log_path", lambda: log_path)
    monkeypatch.setattr(utils, "get_logging_level", lambda: "DEBUG")
    monkeypatch.setattr(logging.handlers, "QueueListener", _NoOpQueueListener)
    monkeypatch.setattr(inspect, "stack", lambda: [])

    logger_name = "test_global_logger_creates_log_dir"
    original_get_logger = logging.getLogger
    test_logger = original_get_logger(logger_name)
    test_logger.handlers.clear()
    monkeypatch.setattr(test_logger, "hasHandlers", lambda: False)
    monkeypatch.setattr(
        logging,
        "getLogger",
        lambda name=None: test_logger if name == logger_name else original_get_logger(name),
    )

    global_logger.loggers.clear()

    logger = global_logger.setup_custom_logger(logger_name)

    assert logger is test_logger
    assert log_path.exists()
    assert log_path.is_dir()

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
