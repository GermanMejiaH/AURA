from __future__ import annotations

from aura.autonomy.executor import AgentExecutor
from aura.autonomy.planner import AgentPlanner
from aura.cognition.deliberation import DeliberationEngine, OutcomeSimulator, StrategySelector
from aura.cognition.goals import (
    GoalManager,
    GoalPrioritizer,
    GoalPriority,
    GoalSelector,
    GoalStatus,
    GoalStore,
)
from aura.events import EventBus, GoalOutcomeRecorded, GoalSelectedForExecution
from aura.memory.episodic import EpisodicMemoryConsolidator
from aura.memory.retrieval import MemoryRetriever
from aura.memory.store import SQLiteMemoryStore


def test_aura_15_full_agency_contract_pipeline(tmp_path):
    """Contract test verifying full end-to-end agency pipeline:
    PersistentGoal -> GoalManager -> GoalPrioritizer -> GoalSelector -> AgentPlanner ->
    DeliberationEngine -> OutcomeSimulator -> StrategySelector -> AgentPlan ->
    AgentExecutor -> ActionVerifier -> CognitiveReflector -> EpisodicMemoryConsolidator ->
    GoalManager.record_execution_outcome() -> Next Selection.
    """
    db_file = str(tmp_path / "agency_contract.db")
    sql_store = SQLiteMemoryStore(db_path=db_file)
    bus = EventBus()

    # 1. Domain persistence & lifecycle manager
    goal_store = GoalStore(store=sql_store)
    goal_manager = GoalManager(store=goal_store, event_bus=bus)

    # 2. Episodic memory consolidator
    consolidator = EpisodicMemoryConsolidator(store=sql_store, event_bus=bus)

    # 3. Deliberation engines
    deliberator = DeliberationEngine()
    retriever = MemoryRetriever(store=sql_store)
    simulator = OutcomeSimulator(memory_retriever=retriever)
    selector = StrategySelector()

    # 4. Planner & Executor
    planner = AgentPlanner(
        event_bus=bus,
        deliberator=deliberator,
        simulator=simulator,
        selector=selector,
    )
    executor = AgentExecutor(event_bus=bus)

    # Track published events
    published_events = []
    bus.subscribe(GoalSelectedForExecution, lambda e: published_events.append(e))
    bus.subscribe(GoalOutcomeRecorded, lambda e: published_events.append(e))

    # 5. Populate Goals
    g_critical = goal_manager.create_goal(
        description="Fix primary power junction",
        priority=GoalPriority.CRITICAL,
        constraints=["Do not disrupt backup power"],
        success_criteria=["Junction voltage normal"],
    )
    g_secondary = goal_manager.create_goal(
        description="Calibrate thermal sensors",
        priority=GoalPriority.HIGH,
    )

    # 6. Execute Goal Cycle 1 (Critical Goal)
    prioritizer = GoalPrioritizer()
    goal_selector = GoalSelector()

    selected1, selection1, plan1, exec1 = planner.execute_goal_cycle(
        goal_manager=goal_manager,
        executor=executor,
        prioritizer=prioritizer,
        selector=goal_selector,
    )

    # Assertions for Cycle 1
    assert selected1 is not None
    assert selected1.goal.goal_id == g_critical.goal_id
    assert selection1 is not None
    assert plan1 is not None
    assert plan1.strategy_id == selection1.chosen_strategy.strategy_id
    assert exec1 is not None
    assert exec1.completed is True

    # Verify GoalManager updated status to COMPLETED
    updated_critical = goal_manager.get_goal(g_critical.goal_id)
    assert updated_critical is not None
    assert updated_critical.status == GoalStatus.COMPLETED
    assert updated_critical.progress.completion_percentage == 100.0

    # Verify events published
    selected_events = [e for e in published_events if isinstance(e, GoalSelectedForExecution)]
    outcome_events = [e for e in published_events if isinstance(e, GoalOutcomeRecorded)]
    assert len(selected_events) == 1
    assert selected_events[0].goal_id == g_critical.goal_id
    assert len(outcome_events) == 1
    assert outcome_events[0].goal_id == g_critical.goal_id
    assert outcome_events[0].status == GoalStatus.COMPLETED.value

    # Verify Episodic Memory recorded the episode
    episodes = consolidator.episodic_memory.search_episodes("power junction")
    assert len(episodes) > 0

    # 7. Execute Goal Cycle 2 (Advances to Secondary Goal)
    selected2, _selection2, _plan2, _exec2 = planner.execute_goal_cycle(
        goal_manager=goal_manager,
        executor=executor,
        prioritizer=prioritizer,
        selector=goal_selector,
    )

    assert selected2 is not None
    assert selected2.goal.goal_id == g_secondary.goal_id
    assert updated_critical.status == GoalStatus.COMPLETED
    assert goal_manager.get_goal(g_secondary.goal_id).status == GoalStatus.COMPLETED
