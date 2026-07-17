import sys
from loguru import logger
from app.core.config import settings


def setup_logging() -> None:
    """Configure Loguru logging."""
    logger.remove()

    log_level = "DEBUG" if settings.DEBUG else "INFO"

    logger.add(
        sys.stdout,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<magenta>{extra[request_id]}</magenta> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    logger.configure(extra={"request_id": "-"})


__all__ = ["logger", "setup_logging"]
