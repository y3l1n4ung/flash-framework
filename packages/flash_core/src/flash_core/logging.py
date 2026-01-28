import logging
import sys
import time
from contextlib import contextmanager
from contextvars import ContextVar, Token
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Generator, Optional, Union

# Enterprise standard: Context-local storage for request tracing
correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


class TraceFormatter(logging.Formatter):
    """
    Formatter that injects tracing metadata and enforces UTC.
    """

    def __init__(self, fmt: str | None = None, datefmt: str | None = None):
        super().__init__(fmt, datefmt)
        # FORCE UTC: Critical for distributed systems to avoid timezone ambiguity
        self.converter = time.gmtime

    def format_time(self, record, datefmt=None):
        """Overridden to ensure strict ISO-8601 UTC format."""
        ct = self.converter(record.created)
        if datefmt:
            s = time.strftime(datefmt, ct)
        else:
            t = time.strftime("%Y-%m-%d %H:%M:%S", ct)
            s = "%s.%03dZ" % (t, record.msecs)
        return s

    def format(self, record: logging.LogRecord) -> str:
        cid = correlation_id.get()
        # Inject 'cid' into the record for the format string
        # We use a distinct attribute name to avoid collisions with extra={}
        record.trace_str = f"[{cid}] " if cid else ""
        return super().format(record)


def get_logger(name: str) -> logging.Logger:
    """
    Returns a standard logger instance.

    In production, always name loggers with dot-notation matching the file path:
    >>> logger = get_logger(__name__)
    """
    return logging.getLogger(name)


def setup_logging(
    level: Union[int, str] = logging.INFO,
    log_file: Optional[Union[str, Path]] = None,
    max_bytes: int = 10_485_760,  # 10MB
    backup_count: int = 10,
    capture_roots: bool = True,  # If True, captures third-party logs (requests, etc)
    module_name: str = "flash",  # The main namespace for your app
) -> None:
    """
    Global logging configuration.

    Args:
        level: Logging level (INFO, DEBUG, etc.)
        log_file: Path to write logs to.
        capture_roots: If True, configures the root logger.
                       If False, only configures 'flash.*' loggers.
    """
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    # Determine which logger to configure: Root or specific namespace
    target_logger = (
        logging.getLogger() if capture_roots else logging.getLogger(module_name)
    )

    # 1. Reset Handlers (Allows reconfiguration during tests)
    target_logger.handlers.clear()

    target_logger.setLevel(level)

    # Enterprise format: ISO-UTC Timestamp, Level, TraceID, Logger, Message
    # Note: %(trace_str)s is injected by TraceFormatter
    log_format = "%(asctime)s %(levelname)-8s %(trace_str)s%(name)s: %(message)s"
    formatter = TraceFormatter(log_format)

    # 2. Stdout Handler (Standard for Containerized Envs)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    target_logger.addHandler(console)

    # 3. File Handler
    if log_file:
        file_path = Path(log_file).resolve()
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = RotatingFileHandler(
                file_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            target_logger.addHandler(file_handler)
        except OSError as e:
            # Fallback if file system is not writable (common in read-only containers)
            sys.stderr.write(f"Failed to setup log file: {e}\n")

    # If we are strictly using the module logger, stop propagation to avoid duplicates
    if not capture_roots:
        target_logger.propagate = False


def set_correlation_id(value: str) -> Token:
    """
    Sets the trace ID and returns a token for cleanup.

    >>> token = set_correlation_id("req-555")
    >>> # ... do work ...
    >>> reset_correlation_id(token)
    """
    return correlation_id.set(value)


def reset_correlation_id(token: Token) -> None:
    """
    Resets the correlation ID to its previous state.
    """
    correlation_id.reset(token)


@contextmanager
def scoped_correlation_id(value: str) -> Generator[None, None, None]:
    """
    Context manager for auto-cleaning trace IDs.

    >>> with scoped_correlation_id("req-123"):
    ...     # Trace ID is set here automatically
    ...     pass
    """
    token = set_correlation_id(value)
    try:
        yield
    finally:
        reset_correlation_id(token)
