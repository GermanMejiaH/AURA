from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..events import EventBus


class LearningEngine:
    """Adapts system policies based on execution feedback and continuous experience."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus
        self.policy_version: float = 1.0

    def record_feedback(self, goal_id: str, success: bool) -> None:
        if success:
            self.policy_version = round(self.policy_version + 0.1, 2)
            if self.event_bus is not None:
                from ..events import PolicyUpdated

                self.event_bus.publish(
                    PolicyUpdated(
                        source="LearningEngine",
                        policy_name="autonomy_policy",
                        version=str(self.policy_version),
                    )
                )
