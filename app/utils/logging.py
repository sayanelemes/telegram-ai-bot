import logging
import re
import sys


class SensitiveFilter(logging.Filter):
    """Filter out bot tokens and API keys from logs."""
    _TOKEN_PATTERN = re.compile(r"(\d{8,11}:[A-Za-z0-9_-]{30,40})|(AIzaSy[A-Za-z0-9_-]{33})")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._TOKEN_PATTERN.sub("[REDACTED_SECRET]", record.msg)
        if record.args:
            args_list = []
            for arg in record.args:
                if isinstance(arg, str):
                    args_list.append(self._TOKEN_PATTERN.sub("[REDACTED_SECRET]", arg))
                else:
                    args_list.append(arg)
            record.args = tuple(args_list)
        return True


def setup_logging(log_level: str = "INFO") -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level.upper())

    # Clear existing handlers
    root_logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(SensitiveFilter())
    root_logger.addHandler(console_handler)

    # Silence noisy loggers
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)
