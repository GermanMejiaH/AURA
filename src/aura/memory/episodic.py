from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING, Any

from .models import Episode

if TYPE_CHECKING:
    from ..autonomy.history import AgentExecutionHistoryStore
    from ..events import Event, EventBus
    from .store import MemoryStore, SQLiteMemoryStore


SENSITIVE_PATTERNS = (
    "password",
    "secret",
    "api_key",
    "token",
    "authorization",
    "bearer",
    "sk-",
    "aiza",
    "_authorized",
    "private_key",
)


def sanitize_metadata(val: Any) -> Any:
    """Recursively sanitizes sensitive key-value pairs and secret strings."""
    if isinstance(val, dict):
        sanitized = {}
        for k, v in val.items():
            k_str = str(k).lower()
            if any(pat in k_str for pat in SENSITIVE_PATTERNS):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_metadata(v)
        return sanitized
    elif isinstance(val, list):
        return [sanitize_metadata(item) for item in val]
    elif isinstance(val, str):
        val_lower = val.lower()
        if any(prefix in val_lower for prefix in ("bearer ", "sk-", "aiza")):
            return "[REDACTED_SECRET]"
        return val
    return val


class EpisodicMemory:
    """Manages episodic long-term memory (experiences, temporal logs, decisions)."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        store: MemoryStore | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.store = store
        self._episodes: list[Episode] = []
        self._lock = threading.RLock()
        if self.store is not None:
            self.load_from_store()

    def load_from_store(self) -> None:
        with self._lock:
            if self.store is not None:
                persisted = self.store.get_episodes(limit=100)
                existing_ids = {e.id for e in self._episodes}
                for ep in persisted:
                    if ep.id not in existing_ids:
                        self._episodes.append(ep)

    def record_episode(self, episode: Episode) -> Episode:
        with self._lock:
            self._episodes.append(episode)
            if self.store is not None:
                self.store.save_episode(episode)

            if self.event_bus is not None:
                from ..events import EpisodeRecorded

                self.event_bus.publish(
                    EpisodeRecorded(
                        source="EpisodicMemory",
                        episode_id=episode.id,
                        summary=episode.summary,
                    )
                )
            return episode

    def search_episodes(self, query: str, limit: int = 5) -> list[Episode]:
        with self._lock:
            if self.store is not None:
                store_results = self.store.get_episodes(query=query, limit=limit)
                if store_results:
                    return store_results

            query_lower = query.lower()
            matching = [
                e
                for e in self._episodes
                if query_lower in e.summary.lower() or query_lower in e.details.lower()
            ]
            return matching[:limit]

    def all_episodes(self) -> list[Episode]:
        with self._lock:
            if self.store is not None:
                store_results = self.store.get_episodes(limit=500)
                if store_results:
                    return store_results
            return list(self._episodes)

    def count(self) -> int:
        with self._lock:
            return len(self.all_episodes())


class EpisodicMemoryConsolidator:
    """Consolidates technical agent execution traces into persistent Episode experiences."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        episodic_memory: EpisodicMemory | None = None,
        history_store: AgentExecutionHistoryStore | None = None,
        store: SQLiteMemoryStore | None = None,
        db_path: str = "data/aura.db",
        container: Any | None = None,
    ) -> None:
        from ..autonomy.history import AgentExecutionHistoryStore
        from .store import MemoryStore, SQLiteMemoryStore

        if store is not None:
            self.store = store
        elif (
            container is not None and hasattr(container, "has") and container.has(SQLiteMemoryStore)
        ):
            self.store = container.resolve(SQLiteMemoryStore)
        elif container is not None and hasattr(container, "has") and container.has(MemoryStore):
            resolved = container.resolve(MemoryStore)
            if isinstance(resolved, SQLiteMemoryStore):
                self.store = resolved
            else:
                self.store = SQLiteMemoryStore(db_path=db_path)
        else:
            self.store = SQLiteMemoryStore(db_path=db_path)
        self.episodic_memory = (
            episodic_memory
            if episodic_memory is not None
            else EpisodicMemory(event_bus=event_bus, store=self.store)
        )
        self.history_store = (
            history_store
            if history_store is not None
            else AgentExecutionHistoryStore(store=self.store, event_bus=event_bus)
        )
        self.event_bus = event_bus
        self._lock = threading.RLock()

        if self.event_bus is not None:
            self.subscribe_to_bus(self.event_bus)

    def subscribe_to_bus(self, event_bus: EventBus) -> None:
        event_bus.subscribe("AgentPlanCompleted", self.handle_event)

    def handle_event(self, event: Event) -> None:
        from ..events import AgentPlanCompleted

        if isinstance(event, AgentPlanCompleted):
            self.consolidate_plan(
                plan_id=event.plan_id,
                event=event,
                verification=getattr(event, "verification", None),
                reflection=getattr(event, "reflection", None),
            )

    def consolidate_plan(
        self,
        plan_id: str,
        event: Any | None = None,
        verification: Any | None = None,
        reflection: Any | None = None,
    ) -> Episode | None:
        with self._lock:
            if not plan_id:
                return None

            episode_id = f"ep_plan_{plan_id}"

            # Idempotency check: return existing if already recorded
            existing = self.episodic_memory.search_episodes(query=plan_id)
            for ep in existing:
                if ep.id == episode_id:
                    return ep

            history_records = self.history_store.get_plan_history(plan_id)
            tree_info = self.history_store.get_plan_execution_tree(plan_id)

            goal_desc = "Plan de Ejecución Agéntica"
            tools_used: list[str] = []
            replans_count = 0
            tasks_summary: list[dict[str, Any]] = []

            for rec in history_records:
                evt_type = rec.get("event_type")
                meta = rec.get("metadata", {})
                if evt_type == "AgentPlanCreated":
                    goal_desc = meta.get("goal_description", goal_desc)
                elif evt_type in ("ToolExecuted", "AgentStepEvaluated"):
                    tool = rec.get("tool_name")
                    if tool and tool not in tools_used:
                        tools_used.append(tool)
                    tasks_summary.append(
                        {
                            "task_id": rec.get("task_id"),
                            "status": rec.get("status"),
                            "tool_name": tool,
                        }
                    )
                elif evt_type in ("AgentReplanned", "AgentReplanRequested"):
                    replan_val = rec.get("replan_count", 0)
                    if isinstance(replan_val, int):
                        replans_count = max(replans_count, replan_val)

            if event is not None:
                completed = getattr(event, "completed", True)
                failed = getattr(event, "failed", False)
                outcome = (
                    "SUCCESS" if completed else ("FAILED" if failed else "WAITING_CONFIRMATION")
                )
            else:
                outcome = tree_info.get("status", "COMPLETED")

            sanitized_goal = sanitize_metadata(goal_desc)
            sanitized_tools = sanitize_metadata(tools_used)
            sanitized_tasks = sanitize_metadata(tasks_summary)

            ver_obj = verification or (getattr(event, "verification", None) if event else None)
            ref_obj = reflection or (getattr(event, "reflection", None) if event else None)

            summary = (
                f"Ejecución agéntica '{sanitized_goal}' terminada con resultado {outcome}. "
                f"Herramientas: {', '.join(sanitized_tools) if sanitized_tools else 'Ninguna'}. "
                f"Re-planificaciones: {replans_count}."
            )

            details_dict: dict[str, Any] = {
                "plan_id": plan_id,
                "goal_description": sanitized_goal,
                "outcome": outcome,
                "replans": replans_count,
                "tools_used": sanitized_tools,
                "strategy": sanitized_tools,
                "tasks": sanitized_tasks,
                "formatted_tree": tree_info.get("formatted_tree", ""),
            }

            if event is not None:
                strat_id = getattr(event, "strategy_id", None)
                strat_name = getattr(event, "strategy_name", None)
                if strat_id:
                    details_dict["strategy_id"] = str(strat_id)
                if strat_name:
                    details_dict["strategy_name"] = str(strat_name)

            if ver_obj is not None:
                ver_status = (
                    ver_obj.status.value
                    if hasattr(ver_obj.status, "value")
                    else str(ver_obj.status)
                )
                details_dict["verification_status"] = ver_status
                details_dict["verification_confidence"] = getattr(ver_obj, "confidence", 1.0)

            if ref_obj is not None:
                root_cause = sanitize_metadata(getattr(ref_obj, "root_cause", ""))
                hypotheses = sanitize_metadata(list(getattr(ref_obj, "hypotheses", [])))
                lesson = sanitize_metadata(getattr(ref_obj, "lesson_learned", ""))
                rec_act = sanitize_metadata(getattr(ref_obj, "recommended_action", ""))
                ref_sev = getattr(ref_obj, "severity", "")
                sev_val = ref_sev.value if hasattr(ref_sev, "value") else str(ref_sev)

                details_dict["root_cause"] = root_cause
                details_dict["hypotheses"] = hypotheses
                details_dict["lesson_learned"] = lesson
                details_dict["recommended_action"] = rec_act
                details_dict["reflection_severity"] = sev_val
                details_dict["reflection_confidence"] = getattr(ref_obj, "confidence", 1.0)

                if lesson:
                    summary += f" Lección aprendida: {lesson}."

            episode = Episode(
                id=episode_id,
                summary=summary,
                details=json.dumps(details_dict),
                tags=["agent_plan", "episodic_experience", str(outcome).lower()],
                importance=1.0,
            )

            self.episodic_memory.record_episode(episode)
            return episode
