import logging


class LoggerProxy:

    def __init__(self, name):
        self._logger = logging.getLogger(name)

    def info(self, message, *args, **kwargs):
        self._logger.info(message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        self._logger.warning(message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        self._logger.error(message, *args, **kwargs)

    def exception(self, message, *args, **kwargs):
        self._logger.exception(message, *args, **kwargs)
