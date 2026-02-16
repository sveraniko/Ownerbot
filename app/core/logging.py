from __future__ import annotations

import logging
from contextvars import ContextVar

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "correlation_id"):
            record.correlation_id = correlation_id_var.get() or "-"
        return True


def configure_logging(level: str) -> None:
    # Create handler with filter
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s correlation_id=%(correlation_id)s %(message)s"
    ))
    handler.addFilter(CorrelationIdFilter())
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    
    # Add filter to all existing loggers
    for logger_name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        for h in logger.handlers:
            h.addFilter(CorrelationIdFilter())


def set_correlation_id(value: str) -> None:
    correlation_id_var.set(value)


def get_correlation_id() -> str:
    return correlation_id_var.get() or "-"
