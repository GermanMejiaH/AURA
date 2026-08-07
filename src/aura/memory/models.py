from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class Episode:
    summary: str
    details: str = ""
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=_utcnow)
    tags: list[str] = field(default_factory=list)
    importance: float = 1.0


@dataclass
class Fact:
    subject: str
    predicate: str
    object_val: str
    id: str = field(default_factory=lambda: str(uuid4()))
    confidence: float = 1.0
    source: str = "system"
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class Preference:
    key: str
    value: str
    category: str = "general"
    updated_at: datetime = field(default_factory=_utcnow)


@dataclass
class MemoryQueryResult:
    episodes: list[Episode] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    preferences: list[Preference] = field(default_factory=list)
