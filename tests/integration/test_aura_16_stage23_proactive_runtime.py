"""Stage 23 Integration Test Suite — Proactive Assistant Runtime & Event-Driven Autonomy.

Verifies test scenarios S23-01 through S23-20:
- Proactive Task Contract & Serialization (S23-01)
- Persistent Task Store & SQLite Operations (S23-02, S23-03, S23-04, S23-05)
- Task Cancellation (S23-06)
- Process Restart Survival (S23-07)
- Trigger Detectors: Time, System Metric, Process, EventBus (S23-08, S23-09, S23-10, S23-11)
- Proposal-Only Invariant: Detector/Evaluator produces proposal only, zero direct execution (S23-12)
- Stage 16 RuntimeOrchestrator Closed-Loop Execution (S23-13)
- Policy & Governance Rejection: Zero Mutation (S23-14, S23-15)
- SAFE_MODE Quarantine Blocking (S23-16)
- Duplicate Event & Concurrent Idempotency Defense (S23-17, S23-18)
- Cross-Conversation Isolation (S23-19)
- Full End-to-End Proactive Assistant Flow (S23-20)
"""

from __future__ import annotations

import tempfile
import threading
from datetime import UTC, datetime, timedelta

from aura.cognition.proactive import (
    ActionProposal,
    EventBusTriggerDetector,
    ProactiveNotification,
    ProactiveTask,
    ProactiveTaskStatus,
    ProactiveTaskStore,
    ProcessConditionDetector,
    SystemConditionDetector,
    TimeTriggerDetector,
    TriggerDefinition,
    TriggerType,
)
from aura.cognition.scheduling.assurance import RuntimeAssuranceEngine
from aura.cognition.scheduling.conversational_runtime import ConversationalRuntime
from aura.cognition.scheduling.orchestration import RuntimeOperationState, RuntimeOrchestrator
from aura.events import Event, EventBus
from aura.memory.store import SQLiteMemoryStore


def test_s23_01_proactive_task_contract_validation() -> None:
    """S23-01: Verify ProactiveTask contract, trigger definitions, and serialization."""
    t_def = TriggerDefinition(
        trigger_type=TriggerType.TIME_CONDITION,
        target_time_iso="2026-12-31T23:59:59+00:00",
    )
    a_prop = ActionProposal(
        tool_name="system_status_tool",
        tool_kwargs={},
        description="Verificar salud del sistema",
    )

    task = ProactiveTask(
        conversation_id="conv_s23_01",
        trigger_type=TriggerType.TIME_CONDITION,
        trigger_definition=t_def,
        action_proposal=a_prop,
        max_executions=1,
    )

    assert task.task_id.startswith("ptask_")
    assert task.status == ProactiveTaskStatus.PENDING
    assert task.execution_count == 0

    d_task = task.to_dict()
    assert d_task["conversation_id"] == "conv_s23_01"
    assert d_task["trigger_type"] == "TIME_CONDITION"

    rebuilt = ProactiveTask.from_dict(d_task)
    assert rebuilt.task_id == task.task_id
    assert rebuilt.trigger_definition.target_time_iso == "2026-12-31T23:59:59+00:00"
    assert rebuilt.action_proposal.tool_name == "system_status_tool"


def test_s23_02_create_persistent_time_based_task() -> None:
    """S23-02: Create persistent time-based task and verify SQLite storage."""
    store = ProactiveTaskStore()

    target_time = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    task = ProactiveTask(
        conversation_id="conv_s23_02",
        trigger_type=TriggerType.TIME_CONDITION,
        trigger_definition=TriggerDefinition(
            trigger_type=TriggerType.TIME_CONDITION, target_time_iso=target_time
        ),
        action_proposal=ActionProposal(tool_name="datetime_tool", tool_kwargs={"action": "now"}),
    )

    store.save_task(task)

    fetched = store.get_task(task.task_id)
    assert fetched is not None
    assert fetched.task_id == task.task_id
    assert fetched.trigger_definition.target_time_iso == target_time


def test_s23_03_create_persistent_system_condition_task() -> None:
    """S23-03: Create persistent system-condition task in ProactiveTaskStore."""
    store = ProactiveTaskStore()

    task = ProactiveTask(
        conversation_id="conv_s23_03",
        trigger_type=TriggerType.SYSTEM_CONDITION,
        trigger_definition=TriggerDefinition(
            trigger_type=TriggerType.SYSTEM_CONDITION,
            metric_name="disk",
            operator="<",
            threshold_value=50.0,
        ),
        action_proposal=ActionProposal(
            tool_name="real_system_observation_tool", tool_kwargs={"action": "disk"}
        ),
    )

    store.save_task(task)

    fetched = store.get_task(task.task_id)
    assert fetched is not None
    assert fetched.trigger_type == TriggerType.SYSTEM_CONDITION
    assert fetched.trigger_definition.metric_name == "disk"
    assert fetched.trigger_definition.threshold_value == 50.0


def test_s23_04_create_process_condition_task() -> None:
    """S23-04: Create process-condition task in ProactiveTaskStore."""
    store = ProactiveTaskStore()

    task = ProactiveTask(
        conversation_id="conv_s23_04",
        trigger_type=TriggerType.PROCESS_CONDITION,
        trigger_definition=TriggerDefinition(
            trigger_type=TriggerType.PROCESS_CONDITION,
            process_name="python.exe",
            extra_params={"expected_state": "running"},
        ),
        action_proposal=ActionProposal(
            tool_name="real_system_observation_tool", tool_kwargs={"action": "processes"}
        ),
    )

    store.save_task(task)

    fetched = store.get_task(task.task_id)
    assert fetched is not None
    assert fetched.trigger_type == TriggerType.PROCESS_CONDITION
    assert fetched.trigger_definition.process_name == "python.exe"


def test_s23_05_retrieve_pending_tasks() -> None:
    """S23-05: Retrieve pending tasks filtered by conversation_id."""
    store = ProactiveTaskStore()

    t1 = ProactiveTask(conversation_id="conv_A", status=ProactiveTaskStatus.PENDING)
    t2 = ProactiveTask(conversation_id="conv_A", status=ProactiveTaskStatus.ACTIVE)
    t3 = ProactiveTask(conversation_id="conv_B", status=ProactiveTaskStatus.PENDING)

    store.save_task(t1)
    store.save_task(t2)
    store.save_task(t3)

    conv_a_tasks = store.list_tasks(conversation_id="conv_A")
    assert len(conv_a_tasks) == 2

    active_tasks = store.list_active_tasks()
    assert len(active_tasks) >= 3


def test_s23_06_cancel_pending_task() -> None:
    """S23-06: Cancel pending task and verify state transition."""
    store = ProactiveTaskStore()

    task = ProactiveTask(conversation_id="conv_s23_06", status=ProactiveTaskStatus.PENDING)
    store.save_task(task)

    cancelled = store.cancel_task(task.task_id, reason="User test cancellation")
    assert cancelled is True

    fetched = store.get_task(task.task_id)
    assert fetched is not None
    assert fetched.status == ProactiveTaskStatus.CANCELLED
    assert fetched.cancellation_reason == "User test cancellation"


def test_s23_07_task_survives_process_restart() -> None:
    """S23-07: Verify persistent proactive tasks survive process restart on file DB."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        db_path = tmp_file.name

    # 1. First process life: Create and persist task
    sqlite_store1 = SQLiteMemoryStore(db_path=db_path)
    task_store1 = ProactiveTaskStore(store=sqlite_store1)

    task = ProactiveTask(
        conversation_id="conv_restart",
        trigger_type=TriggerType.TIME_CONDITION,
        trigger_definition=TriggerDefinition(
            trigger_type=TriggerType.TIME_CONDITION,
            target_time_iso="2026-12-31T00:00:00+00:00",
        ),
        action_proposal=ActionProposal(tool_name="datetime_tool", tool_kwargs={"action": "now"}),
    )
    task_store1.save_task(task)
    sqlite_store1.close()

    # 2. Simulated Process Restart: Re-open DB with new store instance
    sqlite_store2 = SQLiteMemoryStore(db_path=db_path)
    task_store2 = ProactiveTaskStore(store=sqlite_store2)

    active_tasks = task_store2.list_active_tasks()
    assert len(active_tasks) == 1
    assert active_tasks[0].task_id == task.task_id
    assert active_tasks[0].trigger_definition.target_time_iso == "2026-12-31T00:00:00+00:00"
    sqlite_store2.close()


def test_s23_08_time_trigger_detection() -> None:
    """S23-08: TimeTriggerDetector evaluation of past target time and interval."""
    detector = TimeTriggerDetector()

    # Past target time -> should match
    past_iso = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
    t1 = ProactiveTask(
        trigger_type=TriggerType.TIME_CONDITION,
        trigger_definition=TriggerDefinition(
            trigger_type=TriggerType.TIME_CONDITION, target_time_iso=past_iso
        ),
    )
    assert detector.evaluate_trigger(t1) is True

    # Future target time -> should NOT match
    future_iso = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    t2 = ProactiveTask(
        trigger_type=TriggerType.TIME_CONDITION,
        trigger_definition=TriggerDefinition(
            trigger_type=TriggerType.TIME_CONDITION, target_time_iso=future_iso
        ),
    )
    assert detector.evaluate_trigger(t2) is False


def test_s23_09_system_condition_trigger_detection() -> None:
    """S23-09: SystemConditionDetector evaluation of host metrics."""
    detector = SystemConditionDetector()

    # CPU > -1.0% (Always True for non-negative CPU usage)
    task_cpu = ProactiveTask(
        trigger_type=TriggerType.SYSTEM_CONDITION,
        trigger_definition=TriggerDefinition(
            trigger_type=TriggerType.SYSTEM_CONDITION,
            metric_name="cpu",
            operator=">",
            threshold_value=-1.0,
        ),
    )
    assert detector.evaluate_trigger(task_cpu) is True

    # CPU > 999.0% (Always False)
    task_false = ProactiveTask(
        trigger_type=TriggerType.SYSTEM_CONDITION,
        trigger_definition=TriggerDefinition(
            trigger_type=TriggerType.SYSTEM_CONDITION,
            metric_name="cpu",
            operator=">",
            threshold_value=999.0,
        ),
    )
    assert detector.evaluate_trigger(task_false) is False


def test_s23_10_process_completion_trigger_detection() -> None:
    """S23-10: ProcessConditionDetector evaluation of process state."""
    detector = ProcessConditionDetector()

    # Non-existent process terminated -> True
    task_proc = ProactiveTask(
        trigger_type=TriggerType.PROCESS_CONDITION,
        trigger_definition=TriggerDefinition(
            trigger_type=TriggerType.PROCESS_CONDITION,
            process_name="non_existent_proc_xyz99.exe",
            extra_params={"expected_state": "terminated"},
        ),
    )
    assert detector.evaluate_trigger(task_proc) is True


def test_s23_11_eventbus_trigger_detection() -> None:
    """S23-11: EventBusTriggerDetector evaluation of domain events."""
    event_bus = EventBus()
    detector = EventBusTriggerDetector(event_bus=event_bus)

    task_evt = ProactiveTask(
        trigger_type=TriggerType.EVENT_CONDITION,
        trigger_definition=TriggerDefinition(
            trigger_type=TriggerType.EVENT_CONDITION,
            event_name="SystemReady",
        ),
    )

    # Before event published -> False
    assert detector.evaluate_trigger(task_evt) is False

    # Publish SystemReady domain event
    event_bus.publish(Event(source="test", payload={}))  # Generic event -> won't match
    assert detector.evaluate_trigger(task_evt) is False

    # Publish matching event
    class SystemReady(Event):
        pass

    event_bus.publish(SystemReady())
    assert detector.evaluate_trigger(task_evt) is True


def test_s23_12_trigger_produces_proposal_only() -> None:
    """S23-12: Proof that detectors produce proposals ONLY and cannot execute tools."""
    detector = TimeTriggerDetector()

    past_iso = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
    task = ProactiveTask(
        trigger_type=TriggerType.TIME_CONDITION,
        trigger_definition=TriggerDefinition(
            trigger_type=TriggerType.TIME_CONDITION, target_time_iso=past_iso
        ),
        action_proposal=ActionProposal(
            tool_name="datetime_tool", tool_kwargs={"action": "now"}, description="Check time"
        ),
    )

    # 1. Detector evaluation returns boolean match only
    matched = detector.evaluate_trigger(task)
    assert matched is True

    # 2. Inspect task object: zero execution attributes mutated
    assert task.status == ProactiveTaskStatus.PENDING
    assert task.execution_count == 0
    assert task.last_execution_id is None

    # 3. Action proposal remains purely descriptive
    assert task.action_proposal.tool_name == "datetime_tool"
    assert not hasattr(detector, "execute")


def test_s23_13_proposal_dispatches_through_stage16_orchestrator() -> None:
    """S23-13: Verify proactive proposal executes strictly through Stage 16 Orchestrator."""
    runtime = ConversationalRuntime()

    # Create task with past target time so it triggers immediately
    past_iso = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
    _task = runtime.create_proactive_task(
        conversation_id="s23_13_conv",
        trigger_type=TriggerType.TIME_CONDITION,
        trigger_definition=TriggerDefinition(
            trigger_type=TriggerType.TIME_CONDITION, target_time_iso=past_iso
        ),
        action_proposal=ActionProposal(
            tool_name="real_system_observation_tool",
            tool_kwargs={"action": "cpu"},
            description="Observar CPU proactivamente",
        ),
    )

    notifications = runtime.evaluate_proactive_tasks()
    assert len(notifications) == 1

    notif = notifications[0]
    assert notif.success is True
    assert notif.operation_id is not None
    assert "Acción 'Observar CPU proactivamente' ejecutada con éxito" in notif.content

    # Check Stage 16 operation record
    op = runtime.orchestrator.store.get_operation(notif.operation_id)
    assert op is not None
    assert op.state == RuntimeOperationState.COMPLETED
    assert op.action_id == "real_system_observation_tool"

    runtime.close()


def test_s23_14_policy_rejection_zero_mutation() -> None:
    """S23-14: Policy rejection produces ZERO side-effects / zero mutation."""
    runtime = ConversationalRuntime()

    # Create task with invalid/forbidden action parameters
    past_iso = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
    task = runtime.create_proactive_task(
        conversation_id="s23_14_conv",
        trigger_type=TriggerType.TIME_CONDITION,
        trigger_definition=TriggerDefinition(
            trigger_type=TriggerType.TIME_CONDITION, target_time_iso=past_iso
        ),
        action_proposal=ActionProposal(
            tool_name="real_sandboxed_file_tool",
            tool_kwargs={"action": "write", "path": "../../etc/shadow", "content": "hack"},
            description="Escritura fuera de sandbox",
        ),
    )

    notifications = runtime.evaluate_proactive_tasks()
    assert len(notifications) == 1
    assert notifications[0].success is False

    # Verify task state in SQLite
    updated_task = runtime.proactive_store.get_task(task.task_id)
    assert updated_task is not None
    assert updated_task.status == ProactiveTaskStatus.FAILED

    runtime.close()


def test_s23_15_governance_rejection_zero_mutation() -> None:
    """S23-15: Governance rejection produces zero side-effects."""
    runtime = ConversationalRuntime()

    past_iso = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
    _task = runtime.create_proactive_task(
        conversation_id="s23_15_conv",
        trigger_type=TriggerType.TIME_CONDITION,
        trigger_definition=TriggerDefinition(
            trigger_type=TriggerType.TIME_CONDITION, target_time_iso=past_iso
        ),
        action_proposal=ActionProposal(
            tool_name="real_sandboxed_file_tool",
            tool_kwargs={"action": "write", "path": "../outside.txt", "content": "test"},
        ),
    )

    notifications = runtime.evaluate_proactive_tasks()
    assert len(notifications) == 1
    assert notifications[0].success is False

    runtime.close()


def test_s23_16_safe_mode_quarantine_blocks_proactive_execution() -> None:
    """S23-16: SAFE_MODE quarantine blocks proactive task execution cleanly."""
    assurance = RuntimeAssuranceEngine()
    assurance.enter_safe_mode(reason="Proactive quarantine test")

    orchestrator = RuntimeOrchestrator(assurance_engine=assurance)
    runtime = ConversationalRuntime(orchestrator=orchestrator)

    past_iso = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
    task = runtime.create_proactive_task(
        conversation_id="s23_16_conv",
        trigger_type=TriggerType.TIME_CONDITION,
        trigger_definition=TriggerDefinition(
            trigger_type=TriggerType.TIME_CONDITION, target_time_iso=past_iso
        ),
        action_proposal=ActionProposal(
            tool_name="real_system_observation_tool", tool_kwargs={"action": "memory"}
        ),
    )

    notifications = runtime.evaluate_proactive_tasks()
    assert len(notifications) == 1
    assert notifications[0].success is False
    assert "BLOQUEADA" in notifications[0].content

    updated_task = runtime.proactive_store.get_task(task.task_id)
    assert updated_task is not None
    assert updated_task.status == ProactiveTaskStatus.BLOCKED

    runtime.close()


def test_s23_17_duplicate_event_does_not_duplicate_execution() -> None:
    """S23-17: Duplicate events or repeated evaluation calls execute task exactly once."""
    runtime = ConversationalRuntime()

    past_iso = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
    task = runtime.create_proactive_task(
        conversation_id="s23_17_conv",
        trigger_type=TriggerType.TIME_CONDITION,
        trigger_definition=TriggerDefinition(
            trigger_type=TriggerType.TIME_CONDITION, target_time_iso=past_iso
        ),
        action_proposal=ActionProposal(
            tool_name="datetime_tool", tool_kwargs={"action": "now"}
        ),
        max_executions=1,
    )

    # 1. First Evaluation -> Executes
    notifs1 = runtime.evaluate_proactive_tasks()
    assert len(notifs1) == 1
    assert notifs1[0].success is True

    # 2. Duplicate Evaluation -> Task is COMPLETED, should NOT re-trigger
    notifs2 = runtime.evaluate_proactive_tasks()
    assert len(notifs2) == 0

    updated_task = runtime.proactive_store.get_task(task.task_id)
    assert updated_task is not None
    assert updated_task.status == ProactiveTaskStatus.COMPLETED
    assert updated_task.execution_count == 1

    runtime.close()


def test_s23_18_idempotent_concurrent_trigger_evaluation() -> None:
    """S23-18: Verify atomic SQLite claiming prevents concurrent multi-thread executions."""
    runtime = ConversationalRuntime()

    past_iso = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
    task = runtime.create_proactive_task(
        conversation_id="s23_18_conv",
        trigger_type=TriggerType.TIME_CONDITION,
        trigger_definition=TriggerDefinition(
            trigger_type=TriggerType.TIME_CONDITION, target_time_iso=past_iso
        ),
        action_proposal=ActionProposal(
            tool_name="datetime_tool", tool_kwargs={"action": "now"}
        ),
        max_executions=1,
    )

    all_notifications: list[ProactiveNotification] = []
    lock = threading.Lock()

    def _worker() -> None:
        notifs = runtime.evaluate_proactive_tasks()
        with lock:
            all_notifications.extend(notifs)

    threads = [threading.Thread(target=_worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Exactly 1 thread succeeds in claiming and executing the task
    assert len(all_notifications) == 1
    assert all_notifications[0].success is True

    updated_task = runtime.proactive_store.get_task(task.task_id)
    assert updated_task is not None
    assert updated_task.execution_count == 1

    runtime.close()


def test_s23_19_cross_conversation_task_isolation() -> None:
    """S23-19: Verify task listing and notifications remain strictly isolated by conversation_id."""
    runtime = ConversationalRuntime()

    runtime.create_proactive_task(
        conversation_id="user_alice_conv",
        trigger_type=TriggerType.TIME_CONDITION,
        trigger_definition=TriggerDefinition(
            trigger_type=TriggerType.TIME_CONDITION,
            target_time_iso="2026-12-31T00:00:00+00:00",
        ),
        action_proposal=ActionProposal(tool_name="datetime_tool", tool_kwargs={"action": "now"}),
    )

    runtime.create_proactive_task(
        conversation_id="user_bob_conv",
        trigger_type=TriggerType.TIME_CONDITION,
        trigger_definition=TriggerDefinition(
            trigger_type=TriggerType.TIME_CONDITION,
            target_time_iso="2026-12-31T00:00:00+00:00",
        ),
        action_proposal=ActionProposal(tool_name="datetime_tool", tool_kwargs={"action": "now"}),
    )

    alice_tasks = runtime.list_proactive_tasks(conversation_id="user_alice_conv")
    assert len(alice_tasks) == 1
    assert alice_tasks[0].conversation_id == "user_alice_conv"

    bob_tasks = runtime.list_proactive_tasks(conversation_id="user_bob_conv")
    assert len(bob_tasks) == 1
    assert bob_tasks[0].conversation_id == "user_bob_conv"

    runtime.close()


def test_s23_20_full_end_to_end_proactive_assistant_flow() -> None:
    """S23-20: Full end-to-end proactive assistant flow from task creation to notification."""
    runtime = ConversationalRuntime()

    # 1. User turn requests proactive monitoring task
    _task = runtime.create_proactive_task(
        conversation_id="e2e_conv_1",
        trigger_type=TriggerType.SYSTEM_CONDITION,
        trigger_definition=TriggerDefinition(
            trigger_type=TriggerType.SYSTEM_CONDITION,
            metric_name="cpu",
            operator=">",
            threshold_value=-1.0,
        ),
        action_proposal=ActionProposal(
            tool_name="real_system_observation_tool",
            tool_kwargs={"action": "all"},
            description="Verificar métricas completas del sistema host",
        ),
    )

    # 2. Autonomous proactive tick / trigger evaluation
    notifications = runtime.evaluate_proactive_tasks()
    assert len(notifications) == 1

    notif = notifications[0]
    assert notif.success is True
    assert notif.conversation_id == "e2e_conv_1"
    assert "Verificar métricas completas del sistema host" in notif.title

    # 3. Grounded result retrieved for conversational response or TTS
    stored_notifs = runtime.get_proactive_notifications(conversation_id="e2e_conv_1")
    assert len(stored_notifs) == 1
    assert stored_notifs[0].notification_id == notif.notification_id

    runtime.close()
