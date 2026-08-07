from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from ..config import ConfigurationManager
from ..logging import get_logger

JobFn = Callable[..., Any]


@dataclass
class ScheduledJob:
    id: UUID
    name: str
    func: JobFn
    scheduled_at: datetime
    interval: timedelta | None
    recurring: bool
    cancelled: bool = False
    last_run: datetime | None = None
    run_count: int = 0
    error_count: int = 0


@dataclass
class Scheduler:
    config: ConfigurationManager | None = None
    _jobs: list[ScheduledJob] = field(default_factory=list)
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _thread: threading.Thread | None = None
    _stop_event: threading.Event = field(default_factory=threading.Event)
    _running: bool = False
    _max_workers: int = 4

    def start(self) -> None:
        if self._running:
            return
        self._max_workers = (
            self.config.get_typed("scheduler.max_workers", int, 4)
            if self.config is not None
            else 4
        )
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="AuraScheduler", daemon=True)
        self._thread.start()
        logger = get_logger("Scheduler")
        logger.info(f"Scheduler started (max_workers={self._max_workers})")

    def stop(self, timeout: float = 5.0) -> None:
        if not self._running:
            return
        self._running = False
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        logger = get_logger("Scheduler")
        logger.info("Scheduler stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def schedule_once(
        self,
        name: str,
        func: JobFn,
        when: datetime | timedelta | float,
    ) -> UUID:
        scheduled = self._to_datetime(when)
        job = ScheduledJob(
            id=uuid4(),
            name=name,
            func=func,
            scheduled_at=scheduled,
            interval=None,
            recurring=False,
        )
        with self._lock:
            self._jobs.append(job)
        logger = get_logger("Scheduler")
        logger.debug(f"Scheduled one-shot job '{name}' for {scheduled.isoformat()}")
        return job.id

    def schedule_periodic(
        self,
        name: str,
        func: JobFn,
        interval: timedelta | float,
        start: datetime | None = None,
    ) -> UUID:
        td = interval if isinstance(interval, timedelta) else timedelta(seconds=float(interval))
        first = start or (datetime.now(UTC) + td)
        job = ScheduledJob(
            id=uuid4(),
            name=name,
            func=func,
            scheduled_at=first,
            interval=td,
            recurring=True,
        )
        with self._lock:
            self._jobs.append(job)
        logger = get_logger("Scheduler")
        logger.debug(
            f"Scheduled periodic job '{name}' every {td.total_seconds():.1f}s"
        )
        return job.id

    def cancel(self, job_id: UUID) -> bool:
        with self._lock:
            for job in self._jobs:
                if job.id == job_id:
                    job.cancelled = True
                    return True
        return False

    def list_jobs(self) -> list[ScheduledJob]:
        with self._lock:
            return [
                ScheduledJob(
                    id=j.id,
                    name=j.name,
                    func=j.func,
                    scheduled_at=j.scheduled_at,
                    interval=j.interval,
                    recurring=j.recurring,
                    cancelled=j.cancelled,
                    last_run=j.last_run,
                    run_count=j.run_count,
                    error_count=j.error_count,
                )
                for j in self._jobs
            ]

    def pending_count(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs if not j.cancelled)

    def clear(self) -> None:
        with self._lock:
            self._jobs.clear()

    @staticmethod
    def _to_datetime(when: datetime | timedelta | float) -> datetime:
        if isinstance(when, datetime):
            return when
        if isinstance(when, timedelta):
            return datetime.now(UTC) + when
        return datetime.now(UTC) + timedelta(seconds=float(when))

    def _loop(self) -> None:
        logger = get_logger("Scheduler")
        while self._running:
            try:
                if self._stop_event.wait(0.25):
                    break
                self._tick()
            except Exception:
                logger.exception("Scheduler loop error")

    def _tick(self) -> None:
        now = datetime.now(UTC)
        due: list[ScheduledJob] = []
        with self._lock:
            for job in self._jobs:
                if job.cancelled:
                    continue
                if job.scheduled_at <= now:
                    due.append(job)
            self._jobs = [j for j in self._jobs if not (j.cancelled and not j.recurring)]
            self._jobs = [
                j for j in self._jobs if j.recurring or not (j in due and not j.recurring)
            ]

        for job in due:
            self._execute(job)

        with self._lock:
            self._jobs = [j for j in self._jobs if not (j.cancelled and j.last_run is not None)]

    def _execute(self, job: ScheduledJob) -> None:
        logger = get_logger("Scheduler")
        try:
            job.last_run = datetime.now(UTC)
            job.run_count += 1
            job.func()
        except Exception:
            job.error_count += 1
            logger.exception(f"Job '{job.name}' failed")
        finally:
            if job.recurring and job.interval is not None and not job.cancelled:
                job.scheduled_at = datetime.now(UTC) + job.interval
