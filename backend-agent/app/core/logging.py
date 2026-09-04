"""backend-agent 日志配置。"""

from __future__ import annotations

import logging

LOGGER_NAME = "backend_agent"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: str) -> None:
    """配置 Agent 日志级别，并在独立运行时提供默认输出格式。

    Args:
        level: 标准 Python 日志级别名称。
    """
    numeric_level = logging.getLevelNamesMapping()[level]
    logging.getLogger(LOGGER_NAME).setLevel(numeric_level)
    if not logging.getLogger().handlers:
        logging.basicConfig(level=numeric_level, format=LOG_FORMAT)
