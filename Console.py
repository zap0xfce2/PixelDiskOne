import coloredlogs  # type: ignore
import logging

coloredlogs.DEFAULT_DATE_FORMAT = "%d.%m.%y - %H:%M:%S"
coloredlogs.DEFAULT_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
coloredlogs.install(level="INFO")
logger = logging.getLogger(__name__)


def info(message):
    return logger.info(message)


def debug(message):
    return logger.debug(message)


def warning(message):
    return logger.warning(message)


def error(message):
    return logger.error(message)
