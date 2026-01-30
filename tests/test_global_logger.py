import inspect
import logging
from pathlib import Path

from tksessentials import global_logger, utils


class _NoOpQueueListener:
    def __init__(self, *args, **kwargs):
        self.handlers = args[1:]

    def start(self):
        return None


def test_setup_custom_logger_creates_log_dir(tmp_path, monkeypatch):
    log_path = tmp_path / "logs"
    log_path.mkdir(parents=True, exist_ok=True)

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


def test_setup_custom_logger_writes_utf8_mandarin(tmp_path, monkeypatch):
    log_path = tmp_path / "logs"
    log_path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(utils, "get_log_path", lambda: log_path)
    monkeypatch.setattr(utils, "get_logging_level", lambda: "DEBUG")
    monkeypatch.setattr(inspect, "stack", lambda: [])

    captured = {}

    class _CapturingQueueListener:
        def __init__(self, queue, *handlers, **kwargs):
            self.queue = queue
            self.handlers = handlers
            captured["listener"] = self

        def start(self):
            return None

    monkeypatch.setattr(logging.handlers, "QueueListener", _CapturingQueueListener)

    logger_name = "test_global_logger_writes_utf8_mandarin"
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
    listener = captured["listener"]

    message = "中文日志：你好世界"
    logger.info(message)

    record = listener.queue.get_nowait()
    for handler in listener.handlers:
        handler.handle(record)
        if hasattr(handler, "flush"):
            handler.flush()

    file_handlers = [
        handler
        for handler in listener.handlers
        if isinstance(handler, logging.handlers.TimedRotatingFileHandler)
    ]
    assert file_handlers

    log_file = file_handlers[0].baseFilename
    content = Path(log_file).read_text(encoding="utf-8")
    assert message in content

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    for handler in listener.handlers:
        handler.close()


def test_setup_custom_logger_file_handler_when_env_unset(tmp_path, monkeypatch):
    log_path = tmp_path / "logs"
    log_path.mkdir(parents=True, exist_ok=True)

    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setattr(utils, "get_log_path", lambda: log_path)
    monkeypatch.setattr(utils, "get_logging_level", lambda: "DEBUG")
    monkeypatch.setattr(inspect, "stack", lambda: [])

    captured = {}

    class _CapturingQueueListener:
        def __init__(self, queue, *handlers, **kwargs):
            self.handlers = handlers
            captured["listener"] = self

        def start(self):
            return None

    monkeypatch.setattr(logging.handlers, "QueueListener", _CapturingQueueListener)

    logger_name = "test_global_logger_file_handler_when_env_unset"
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
    listener = captured["listener"]

    assert any(
        isinstance(handler, logging.handlers.TimedRotatingFileHandler)
        for handler in listener.handlers
    )

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    for handler in listener.handlers:
        handler.close()
