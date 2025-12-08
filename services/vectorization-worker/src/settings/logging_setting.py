import sys
import logging
import structlog

def setup_logging(level: str = "INFO") -> None:
    """
    Configure structlog for:
      - async apps (FastAPI / uvicorn)
      - JSON logging
      - safe stack traces
      - no crashes
    """

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,

            # timestamp on every log
            structlog.processors.TimeStamper(fmt="iso"),

            # enable traceback on logger.exception()
            structlog.processors.format_exc_info,

            # ensure valid unicode
            structlog.processors.UnicodeDecoder(),

            # final JSON rendering
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Standard library logging backend
    logging.basicConfig(
        stream=sys.stderr,
        level=getattr(logging, level.upper()),
        force=True,
    )

    # Quiet uvicorn a little
    # logging.getLogger("uvicorn").setLevel(logging.INFO)
    # logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    # logging.getLogger("uvicorn.access").setLevel(logging.WARNING)