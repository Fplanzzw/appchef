# [AppChef 日志] 控制台 + 滚动文件，便于商业化排障与审计
import logging
import sys
from logging.handlers import RotatingFileHandler

from appchef.common.paths import LOGS_DIR

LOG_FORMAT = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
_logger_setup_done = False


def setup_logging() -> None:
    global _logger_setup_done
    if _logger_setup_done:
        return
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter(LOG_FORMAT)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    log_file = LOGS_DIR / "appchef.log"
    fh = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)
    _logger_setup_done = True


logger = logging.getLogger("personal_chief")

