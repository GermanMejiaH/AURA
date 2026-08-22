"""Stage 25.4 — SQLiteMemoryStore Consolidation Unit & Integration Tests.

Validates that:
1. Normal AURA boot creates exactly ONE shared production SQLiteMemoryStore instance.
2. All memory/cognition/scheduling/proactive/autonomy stores share the same object ID.
3. Memory persistence continues working across restarts.
4. Isolated unit tests can still use SQLiteMemoryStore(":memory:").
5. Containerless fallbacks still work when no container or store is provided.
"""

from pathlib import Path

from aura.autonomy.history import AgentExecutionHistoryStore
from aura.cognition.goals.store import GoalStore
from aura.cognition.proactive.store import ProactiveTaskStore
from aura.cognition.scheduling.adaptation import RuntimeAdaptationStore
from aura.cognition.scheduling.assurance import RuntimeAssuranceStore
from aura.cognition.scheduling.experience import RuntimeExperienceStore
from aura.cognition.scheduling.orchestration import RuntimeOrchestrationStore
from aura.cognition.scheduling.persistence import RuntimeHistoryStore, RuntimeStateStore
from aura.cognition.scheduling.store import ScheduleStore
from aura.container import DependencyContainer
from aura.core.aura import AURA, AURABootOptions
from aura.memory.context import CognitiveContextManager
from aura.memory.conversational import ConversationalMemory
from aura.memory.episodic import EpisodicMemoryConsolidator
from aura.memory.module import MemoryModule
from aura.memory.plan_store import AgentPlanStore
from aura.memory.retrieval import MemoryRetriever
from aura.memory.store import MemoryStore, SQLiteMemoryStore


def test_single_production_store_on_boot(tmp_path: Path) -> None:
    """AURA.boot() must instantiate exactly ONE production SQLiteMemoryStore in container."""
    db_file = tmp_path / "test_aura.db"
    opts = AURABootOptions(
        config_paths=(),
        load_env=False,
        enable_audio=False,
        enable_vision=False,
        enable_robotics=False,
    )
    app = AURA(options=opts)
    app.config.set("memory.enabled", True)
    app.config.set("memory.db_path", str(db_file))

    app.boot()

    try:
        assert app.container.has(MemoryStore)
        assert app.container.has(SQLiteMemoryStore)

        store1 = app.container.resolve(MemoryStore)
        store2 = app.container.resolve(SQLiteMemoryStore)

        assert store1 is store2
        assert id(store1) == id(store2)
        assert isinstance(store1, SQLiteMemoryStore)
        assert store1.db_path == str(db_file)
    finally:
        app.shutdown()


def test_all_consumers_share_same_object_id() -> None:
    """All 16 audit consumers must resolve and share the exact same store object ID."""
    container = DependencyContainer()
    shared_store = SQLiteMemoryStore(db_path=":memory:")
    container.register(MemoryStore, instance=shared_store)
    container.register(SQLiteMemoryStore, instance=shared_store)

    shared_id = id(shared_store)

    mem_module = MemoryModule(container=container)
    plan_store = AgentPlanStore(container=container)
    conv_mem = ConversationalMemory(container=container)
    ep_consolidator = EpisodicMemoryConsolidator(container=container)
    retriever = MemoryRetriever(container=container)
    ctx_manager = CognitiveContextManager(container=container)
    goal_store = GoalStore(container=container)
    sched_store = ScheduleStore(container=container)
    sched_pers_store = RuntimeHistoryStore(container=container)
    rt_state_store = RuntimeStateStore(container=container)
    rt_exp_store = RuntimeExperienceStore(container=container)
    rt_adapt_store = RuntimeAdaptationStore(container=container)
    rt_assur_store = RuntimeAssuranceStore(container=container)
    rt_orch_store = RuntimeOrchestrationStore(container=container)
    proactive_store = ProactiveTaskStore(container=container)
    exec_history_store = AgentExecutionHistoryStore(container=container)

    consumer_stores = [
        ("MemoryModule", mem_module.store),
        ("AgentPlanStore", plan_store.store),
        ("ConversationalMemory", conv_mem.store),
        ("EpisodicMemoryConsolidator", ep_consolidator.store),
        ("MemoryRetriever", retriever.store),
        ("CognitiveContextManager", ctx_manager.store),
        ("GoalStore", goal_store._memory_store),
        ("ScheduleStore", sched_store._memory_store),
        ("RuntimeHistoryStore", sched_pers_store._memory_store),
        ("RuntimeStateStore", rt_state_store._memory_store),
        ("RuntimeExperienceStore", rt_exp_store._memory_store),
        ("RuntimeAdaptationStore", rt_adapt_store._memory_store),
        ("RuntimeAssuranceStore", rt_assur_store._memory_store),
        ("RuntimeOrchestrationStore", rt_orch_store.store),
        ("ProactiveTaskStore", proactive_store.store),
        ("AgentExecutionHistoryStore", exec_history_store.store),
    ]

    for name, store_inst in consumer_stores:
        assert store_inst is shared_store, f"{name} did not use shared SQLiteMemoryStore instance"
        assert id(store_inst) == shared_id, f"{name} object ID mismatch"


def test_persistence_survives_restart(tmp_path: Path) -> None:
    """Verifies facts and preferences persisted via SQLiteMemoryStore survive cold reboot."""
    from aura.memory.models import Fact

    db_file = tmp_path / "persistence_test.db"

    # Turn 1: Save data
    store1 = SQLiteMemoryStore(db_path=str(db_file))
    container1 = DependencyContainer()
    container1.register(SQLiteMemoryStore, instance=store1)
    container1.register(MemoryStore, instance=store1)

    mem1 = MemoryModule(container=container1)
    mem1.semantic.add_fact(Fact(subject="user", predicate="color_favorito", object_val="azul"))
    mem1.preferences.set_preference("theme", "dark", category="ui")

    # Turn 2: Cold boot restart
    store2 = SQLiteMemoryStore(db_path=str(db_file))
    container2 = DependencyContainer()
    container2.register(SQLiteMemoryStore, instance=store2)
    container2.register(MemoryStore, instance=store2)

    mem2 = MemoryModule(container=container2)
    facts = mem2.semantic.query_facts(subject="user")
    pref = mem2.preferences.get_preference("theme")

    assert len(facts) > 0
    assert facts[0].object_val == "azul"
    assert pref == "dark"


def test_isolated_memory_store_for_unit_tests() -> None:
    """Verifies isolated unit tests can still pass in-memory store directly."""
    in_mem_store = SQLiteMemoryStore(db_path=":memory:")
    plan_store = AgentPlanStore(store=in_mem_store)
    goal_store = GoalStore(store=in_mem_store)

    assert plan_store.store is in_mem_store
    assert goal_store._memory_store is in_mem_store
    assert in_mem_store.db_path == ":memory:"


def test_containerless_fallback_still_works(tmp_path: Path) -> None:
    """Verifies containerless fallback works when no container or store is injected."""
    custom_db = str(tmp_path / "fallback.db")
    store = GoalStore(db_path=custom_db)

    assert store._memory_store is not None
    assert isinstance(store._memory_store, SQLiteMemoryStore)
    assert store.db_path == custom_db
