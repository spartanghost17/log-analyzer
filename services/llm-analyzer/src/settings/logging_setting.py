import sys
import logging
from typing import Any
import structlog
from structlog.types import Processor


def setup_logging(
        log_level: str = "INFO",
        use_json: bool = False,
        include_callsite: bool = False
) -> None:
    """
    Configure structured logging with color support and flexible formatting.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        use_json: Whether to use JSON formatting (useful for production)
        include_callsite: Whether to include file/line information
    """

    # Determine if we're in a terminal (for color support)
    is_terminal = sys.stderr.isatty()

    # Base processors that are always included
    processors: list[Processor] = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # Add callsite information if requested
    if include_callsite:
        processors.append(
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                    structlog.processors.CallsiteParameter.LINENO,
                ]
            )
        )

    # Choose final processor based on environment and preferences
    if use_json:
        # JSON format for production/structured logging
        processors.append(
            structlog.processors.JSONRenderer(sort_keys=True)
        )
        log_format = "%(message)s"
    elif is_terminal:
        # Colored console output for development
        processors.append(
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.rich_traceback
            )
        )
        log_format = "%(message)s"
    else:
        # Plain console output for non-terminal environments
        processors.append(
            structlog.processors.LogfmtRenderer(key_order=["timestamp", "level", "logger"])
        )
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Configure structlog
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format,
        stream=sys.stderr,
        force=True  # Override any existing configuration
    )

    # Set levels for noisy third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def setup_development_logging() -> None:
    """Convenient preset for development with colors and detailed info."""
    setup_logging(
        log_level="DEBUG",
        use_json=False,
        include_callsite=True
    )


def setup_production_logging() -> None:
    """Convenient preset for production with JSON formatting."""
    setup_logging(
        log_level="INFO",
        use_json=True,
        include_callsite=False
    )


def get_logger(name: str = __name__) -> Any:
    """Get a structured logger instance."""
    return structlog.get_logger(name)