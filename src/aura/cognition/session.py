from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..events import EventBus
    from .intent import Intent


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class SessionContext:
    """Volatile in-RAM cognitive session state active for current conversation."""

    session_id: str = field(default_factory=lambda: f"sess_{uuid.uuid4().hex[:8]}")
    current_topic: str | None = None
    active_task: str | None = None
    task_detail: str | None = None
    active_entity: str | None = None
    last_intent: str | None = None
    turn_count: int = 0
    start_time: datetime = field(default_factory=_utcnow)
    context_variables: dict[str, Any] = field(default_factory=dict)


class SessionManager:
    """Manages active session context in RAM. Reset on reboot or manual session restart."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus
        self._lock = threading.RLock()
        self._context = SessionContext()

    def get_context(self) -> SessionContext:
        with self._lock:
            return SessionContext(
                session_id=self._context.session_id,
                current_topic=self._context.current_topic,
                active_task=self._context.active_task,
                task_detail=self._context.task_detail,
                active_entity=self._context.active_entity,
                last_intent=self._context.last_intent,
                turn_count=self._context.turn_count,
                start_time=self._context.start_time,
                context_variables=dict(self._context.context_variables),
            )

    def record_turn(self) -> int:
        with self._lock:
            self._context.turn_count += 1
            return self._context.turn_count

    def update_intent(self, intent: Intent) -> None:
        with self._lock:
            intent_name = (
                intent.intent_type.value
                if hasattr(intent.intent_type, "value")
                else str(intent.intent_type)
            )
            self._context.last_intent = intent_name

            # Update topic or active task if parameters provide clear evidence
            if intent.parameters.get("topic"):
                self._context.current_topic = str(intent.parameters["topic"])

            if intent.parameters.get("task"):
                self._context.active_task = str(intent.parameters["task"])

            if self.event_bus is not None:
                from ..events import SessionContextUpdated

                self.event_bus.publish(
                    SessionContextUpdated(
                        source="SessionManager",
                        session_id=self._context.session_id,
                        current_topic=self._context.current_topic or "",
                        active_task=self._context.active_task or "",
                        last_intent=self._context.last_intent or "",
                    )
                )

    def set_topic(self, topic: str | None) -> None:
        with self._lock:
            self._context.current_topic = topic

    def clear_topic(self) -> None:
        with self._lock:
            self._context.current_topic = None

    def set_task(self, task: str | None, detail: str | None = None) -> None:
        with self._lock:
            self._context.active_task = task
            if detail is not None:
                self._context.task_detail = detail

    def set_task_detail(self, detail: str | None) -> None:
        with self._lock:
            self._context.task_detail = detail

    def clear_task(self) -> None:
        with self._lock:
            self._context.active_task = None
            self._context.task_detail = None

    def set_active_entity(self, entity: str | None) -> None:
        with self._lock:
            self._context.active_entity = entity

    def clear_active_entity(self) -> None:
        with self._lock:
            self._context.active_entity = None

    def reset_session(self) -> SessionContext:
        with self._lock:
            self._context = SessionContext()
            return self.get_context()
