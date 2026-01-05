import logging
from enum import IntEnum
from typing import Optional


class Level(IntEnum):
    NOTSET = logging.NOTSET
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class Logger:
    _logger: Optional[logging.Logger] = None

    @classmethod
    def configure(cls, name: str, level: Level | int) -> None:
        if cls._logger is not None:
            raise RuntimeError("logger has already been configured")

        logging.basicConfig(
            level=int(level),
            format="%(levelname)s %(name)s: %(message)s",
        )
        cls._logger = logging.getLogger(name)

    @classmethod
    def get(cls) -> logging.Logger:
        if cls._logger is None:
            raise RuntimeError("logger is not configured yet")
        return cls._logger

    # Универсальное логирование
    @classmethod
    def log(cls, level: Level | int, msg: str, *args, **kwargs) -> None:
        cls.get().log(int(level), msg, *args, **kwargs)    
        
    @classmethod
    def debug(cls, msg: str, *args, **kwargs) -> None:
        cls.get().debug(msg, *args, **kwargs)

    @classmethod
    def info(cls, msg: str, *args, **kwargs) -> None:
        cls.get().info(msg, *args, **kwargs)

    @classmethod
    def warning(cls, msg: str, *args, **kwargs) -> None:
        cls.get().warning(msg, *args, **kwargs)

    @classmethod
    def error(cls, msg: str, *args, **kwargs) -> None:
        cls.get().error(msg, *args, **kwargs)

    @classmethod
    def exception(cls, msg: str, *args, **kwargs) -> None:
        cls.get().exception(msg, *args, **kwargs)

    # Настройка уровней сторонних логгеров (telegram/httpx/etc)
    @classmethod
    def set_level(cls, logger_name: str, level: Level | int) -> None:
        logging.getLogger(logger_name).setLevel(int(level))

    @classmethod
    def silence(cls, *logger_names: str, level: Level | int = Level.CRITICAL) -> None:
        for n in logger_names:
            logging.getLogger(n).setLevel(int(level))
            
    @classmethod
    def exception(cls, msg: str, *args, exc_info: bool = True, **kwargs) -> None:
        cls.get().exception(msg, *args, exc_info=exc_info, **kwargs)