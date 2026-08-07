from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from ..events import EventBus, LifecycleStateChanged
from ..logging import get_logger


class SystemState(str, Enum):
    BOOTING = "Booting"
    INITIALIZING = "Initializing"
    RUNNING = "Running"
    DEGRADED = "Degraded"
    SHUTTING_DOWN = "Shutting Down"
    STOPPED = "Stopped"
    RECOVERY = "Recovery"


TRANSITIONS: dict[SystemState, set[SystemState]] = {
    SystemState.BOOTING: {
        SystemState.INITIALIZING,
        SystemState.STOPPED,
        SystemState.RECOVERY,
    },
    SystemState.INITIALIZING: {
        SystemState.RUNNING,
        SystemState.DEGRADED,
        SystemState.STOPPED,
        SystemState.RECOVERY,
    },
    SystemState.RUNNING: {
        SystemState.DEGRADED,
        SystemState.SHUTTING_DOWN,
        SystemState.RECOVERY,
    },
    SystemState.DEGRADED: {
        SystemState.RUNNING,
        SystemState.SHUTTING_DOWN,
        SystemState.RECOVERY,
        SystemState.STOPPED,
    },
    SystemState.SHUTTING_DOWN: {SystemState.STOPPED, SystemState.RECOVERY},
    SystemState.STOPPED: {SystemState.BOOTING, SystemState.RECOVERY},
    SystemState.RECOVERY: {
        SystemState.BOOTING,
        SystemState.INITIALIZING,
        SystemState.RUNNING,
        SystemState.STOPPED,
    },
}


StateTransitionCallback = Callable[[SystemState, SystemState], None]


@dataclass
class LifecycleManager:
    _state: SystemState = SystemState.STOPPED
    _state_history: list[tuple[SystemState, datetime, str]] = field(default_factory=list)
    _transition_callbacks: list[StateTransitionCallback] = field(default_factory=list)
    _bus: EventBus | None = None
    _boot_time: datetime | None = None
    _last_transition_reason: str = "initialized"

    def __post_init__(self) -> None:
        self._record(self._state, "initial")

    @property
    def state(self) -> SystemState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state in {SystemState.RUNNING, SystemState.DEGRADED}

    @property
    def is_booting(self) -> bool:
        return self._state in {SystemState.BOOTING, SystemState.INITIALIZING}

    @property
    def is_stopped(self) -> bool:
        return self._state == SystemState.STOPPED

    @property
    def uptime_seconds(self) -> float:
        if self._boot_time is None:
            return 0.0
        return (datetime.now(UTC) - self._boot_time).total_seconds()

    def attach_bus(self, bus: EventBus) -> None:
        self._bus = bus

    def on_transition(self, callback: StateTransitionCallback) -> None:
        self._transition_callbacks.append(callback)

    def can_transition_to(self, target: SystemState) -> bool:
        return target in TRANSITIONS.get(self._state, set())

    def transition_to(self, target: SystemState, reason: str = "") -> bool:
        if target == self._state:
            return True
        if not self.can_transition_to(target):
            logger = get_logger("LifecycleManager")
            logger.error(
                f"Invalid transition: {self._state.value} -> {target.value} (reason: {reason})"
            )
            return False

        previous = self._state
        self._state = target
        self._last_transition_reason = reason or "no_reason"
        self._record(target, reason)

        if target == SystemState.RUNNING and self._boot_time is None:
            self._boot_time = datetime.now(UTC)
        if target == SystemState.STOPPED:
            self._boot_time = None

        logger = get_logger("LifecycleManager")
        logger.info(
            f"State transition: {previous.value} -> {target.value}"
            + (f" ({reason})" if reason else "")
        )

        for cb in list(self._transition_callbacks):
            try:
                cb(previous, target)
            except Exception:
                logger.exception(f"Lifecycle callback failed for {target.value}")

        if self._bus is not None:
            try:
                self._bus.publish(
                    LifecycleStateChanged(
                        source="LifecycleManager",
                        previous_state=previous.value,
                        new_state=target.value,
                        payload={"reason": reason},
                    )
                )
            except Exception:
                logger.exception("Failed to publish LifecycleStateChanged event")

        return True

    def boot(self) -> bool:
        return self.transition_to(SystemState.BOOTING, "boot_requested")

    def initialize(self) -> bool:
        return self.transition_to(SystemState.INITIALIZING, "initializing_modules")

    def start(self) -> bool:
        return self.transition_to(SystemState.RUNNING, "all_modules_ready")

    def degrade(self, reason: str = "degraded") -> bool:
        return self.transition_to(SystemState.DEGRADED, reason)

    def begin_shutdown(self, reason: str = "manual") -> bool:
        return self.transition_to(SystemState.SHUTTING_DOWN, reason)

    def stop(self, reason: str = "stopped") -> bool:
        return self.transition_to(SystemState.STOPPED, reason)

    def recover(self, reason: str = "recovery_mode") -> bool:
        return self.transition_to(SystemState.RECOVERY, reason)

    def history(self, limit: int | None = None) -> list[tuple[SystemState, datetime, str]]:
        if limit is None:
            return list(self._state_history)
        return list(self._state_history[-limit:])

    def allowed_targets(self) -> list[SystemState]:
        return sorted(TRANSITIONS.get(self._state, set()), key=lambda s: s.value)

    def _record(self, state: SystemState, reason: str) -> None:
        self._state_history.append((state, datetime.now(UTC), reason))
        if len(self._state_history) > 1000:
            self._state_history = self._state_history[-1000:]
