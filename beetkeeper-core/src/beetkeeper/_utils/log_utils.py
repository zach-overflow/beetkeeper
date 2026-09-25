"""
Collection of internal logging utilities, especially -- but not exclusively -- for setting up non-blocking logging for
`async` compat.

See also:
    https://stackoverflow.com/a/70716053
    https://discuss.python.org/t/support-async-logging-module/50130
"""

import logging
import sys
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from queue import Queue
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from beetkeeper.settings import LoggingConfSection


def configure_app_logging(log_conf: LoggingConfSection) -> QueueListener:
    """
    Utility for initializing the log handlers and non-blocking logging setup during application startup.
    Applies all configurations to the root logger to ensure the config is propagated globally during the
    lifetime of the server.

    Returns: The root `logging.handlers.QueueListener` instance which is running in a dedicated background thread.
    """
    log_q: Queue = Queue()
    q_handler = QueueHandler(log_q)
    logging.basicConfig(level=log_conf.log_level, handlers=[q_handler], force=True)
    log_q_listener = QueueListener(log_q, _create_background_thread_log_handler(log_conf=log_conf))
    log_q_listener.start()
    return log_q_listener


def _create_background_thread_log_handler(log_conf: LoggingConfSection) -> logging.StreamHandler | RotatingFileHandler:
    """Creates and returns the proper logging handler run in the background log queue consumer thread."""
    if log_conf.log_filepath is not None:
        return RotatingFileHandler(log_conf.log_filepath, maxBytes=log_conf.log_rotation_max_bytes, backupCount=1)
    return logging.StreamHandler(sys.stdout)
