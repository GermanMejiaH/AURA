from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from logging import Formatter, Handler, LogRecord
from pathlib import Path
from typing import Any, Callable

from ..events import EventBus, LogEntryCreated


_LOG_LEVELS: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "WARN": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
    "FATAL": logging.CRITICAL,
}


class EventBusHandler(Handler):
    def __init__(self, bus: EventBus | None = None, level: int = logging.NOTSET) -> None:
        super().__init__(level=level)
        self._bus = bus

    def attach(self, bus: EventBus) -> None:
        self._bus = bus

    def emit(self, record: LogRecord) -> None:
        if self._bus is None:
            return
        try:
            event = LogEntryCreated(
                source="logging",
                level=record.levelname,
                message=record.getMessage(),
                logger_name=record.name,
                payload={
                    "module": record.module,
                    "funcName": record.funcName,
                    "lineno": record.lineno,
                    "process": record.process,
                    "thread": record.thread,
                },
            )
            self._bus.publish(event)
        except Exception:
            pass


@dataclass
class AuraLogger:
    root_name: str = "aura"
    level: int = logging.INFO
    log_format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    enable_console: bool = True
    enable_file: bool = False
    file_path: str = "aura.log"
    propagate: bool = False

    _configured: bool = False
    _event_handler: EventBusHandler | None = None
    _custom_handlers: list[Handler] = field(default_factory=list)

    def configure(
        self,
        level: str | int | None = None,
        log_format: str | None = None,
        enable_console: bool | None = None,
        enable_file: bool | None = None,
        file_path: str | None = None,
    ) -> None:
        if level is not None:
            self.level = self._parse_level(level)
        if log_format is not None:
            self.log_format = log_format
        if enable_console is not None:
            self.enable_console = enable_console
        if enable_file is not None:
            self.enable_file = enable_file
        if file_path is not None:
            self.file_path = file_path
        self._rebuild()

    def attach_event_bus(self, bus: EventBus) -> None:
        if self._event_handler is None:
            self._event_handler = EventBusHandler(level=self.level)
            self._custom_handlers.append(self._event_handler)
            root = logging.getLogger(self.root_name)
            root.addHandler(self._event_handler)
        self._event_handler.attach(bus)

    def add_handler(self, handler: Handler) -> None:
        self._custom_handlers.append(handler)
        root = logging.getLogger(self.root_name)
        root.addHandler(handler)

    def get_logger(self, name: str | None = None) -> logging.Logger:
        if not self._configured:
            self._rebuild()
        full = f"{self.root_name}.{name}" if name else self.root_name
        return logging.getLogger(full)

    def _rebuild(self) -> None:
        root = logging.getLogger(self.root_name)
        for h in list(root.handlers):
            root.removeHandler(h)
        root.setLevel(self.level)
        root.propagate = self.propagate

        formatter = Formatter(self.log_format)

        if self.enable_console:
            ch = logging.StreamHandler(stream=sys.stdout)
            ch.setLevel(self.level)
            ch.setFormatter(formatter)
            root.addHandler(ch)

        if self.enable_file:
            try:
                Path(self.file_path).parent.mkdir(parents=True, exist_ok=True)
                fh = logging.FileHandler(self.file_path, encoding="utf-8")
                fh.setLevel(self.level)
                fh.setFormatter(formatter)
                root.addHandler(fh)
            except Exception:
                pass

        for h in self._custom_handlers:
            root.addHandler(h)

        self._configured = True

    @staticmethod
    def _parse_level(raw: str | int) -> int:
        if isinstance(raw, int):
            return raw
        return _LOG_LEVELS.get(str(raw).upper(), logging.INFO)


_instance: AuraLogger | None = None


def configure_logging(**kwargs: Any) -> AuraLogger:
    global _instance
    if _instance is None:
        _instance = AuraLogger()
    _instance.configure(**kwargs)
    return _instance


def get_logger(name: str | None = None) -> logging.Logger:
    global _instance
    if _instance is None:
        _instance = AuraLogger()
    return _instance.get_logger(name)


def attach_event_bus(bus: EventBus) -> None:
    global _instance
    if _instance is None:
        _instance = AuraLogger()
    _instance.attach_event_bus(bus)


def set_logger_instance(logger: AuraLogger) -> None:
    global _instance
    _instance = logger
