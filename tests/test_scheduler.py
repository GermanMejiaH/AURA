from __future__ import annotations

import time

from aura.config import ConfigurationManager
from aura.core import Scheduler


def test_scheduler_one_shot_triggered():
    s = Scheduler(config=ConfigurationManager())
    s.start()
    try:
        fired: list[int] = []
        s.schedule_once("inc", lambda: fired.append(1), when=0.01)
        deadline = time.time() + 2.0
        while not fired and time.time() < deadline:
            time.sleep(0.05)
        assert fired == [1]
    finally:
        s.stop()


def test_scheduler_periodic_triggers_multiple_times():
    s = Scheduler(config=ConfigurationManager())
    s.start()
    try:
        fired: list[int] = []
        s.schedule_periodic("inc-2", lambda: fired.append(1), interval=0.05)
        deadline = time.time() + 2.0
        while len(fired) < 3 and time.time() < deadline:
            time.sleep(0.05)
        assert len(fired) >= 3
    finally:
        s.stop()


def test_scheduler_cancel_prevents_execution():
    s = Scheduler(config=ConfigurationManager())
    s.start()
    try:
        fired: list[int] = []
        job_id = s.schedule_once("cancel-me", lambda: fired.append(1), when=0.5)
        assert s.cancel(job_id)
        time.sleep(0.7)
        assert fired == []
    finally:
        s.stop()


def test_scheduler_pending_count_and_list():
    s = Scheduler(config=ConfigurationManager())
    s.schedule_once("a", lambda: None, when=5.0)
    s.schedule_periodic("b", lambda: None, interval=10.0)
    assert s.pending_count() == 2
    jobs = s.list_jobs()
    names = {j.name for j in jobs}
    assert names == {"a", "b"}


def test_scheduler_start_and_stop():
    s = Scheduler()
    assert not s.is_running
    s.start()
    assert s.is_running
    s.stop()
    assert not s.is_running
