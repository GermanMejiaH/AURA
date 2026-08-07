from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4


def _utcnow() -> datetime:
    return datetime.now(UTC)


class EntityType(str, Enum):
    PERSON = "person"
    OBJECT = "object"
    LOCATION = "location"
    DEVICE = "device"
    PET = "pet"
    TASK = "task"
    CONVERSATION = "conversation"
    CAPABILITY = "capability"
    CUSTOM = "custom"


class RelationType(str, Enum):
    LOCATED_IN = "located_in"
    OWNS = "owns"
    BELONGS_TO = "belongs_to"
    FEEDS = "feeds"
    OBSERVES = "observes"
    CAN_EXECUTE = "can_execute"
    CONNECTED_TO = "connected_to"
    CONTAINS = "contains"
    PARTICIPATES_IN = "participates_in"
    CUSTOM = "custom"


@dataclass
class Entity:
    name: str
    type: EntityType | str = EntityType.OBJECT
    id: str = field(default_factory=lambda: str(uuid4()))
    attributes: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source: str = "user"
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    valid_until: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value if isinstance(self.type, Enum) else self.type,
            "attributes": dict(self.attributes),
            "confidence": self.confidence,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Entity:
        type_val: EntityType | str = data.get("type", EntityType.OBJECT)
        try:
            type_val = EntityType(type_val)
        except ValueError:
            pass

        created_at = (
            datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else _utcnow()
        )
        updated_at = (
            datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else _utcnow()
        )
        valid_until = (
            datetime.fromisoformat(data["valid_until"])
            if data.get("valid_until")
            else None
        )

        return cls(
            id=data["id"],
            name=data["name"],
            type=type_val,
            attributes=dict(data.get("attributes", {})),
            confidence=float(data.get("confidence", 1.0)),
            source=str(data.get("source", "system")),
            created_at=created_at,
            updated_at=updated_at,
            valid_until=valid_until,
        )


@dataclass
class Relation:
    source_id: str
    target_id: str
    relation_type: RelationType | str = RelationType.CONNECTED_TO
    id: str = field(default_factory=lambda: str(uuid4()))
    attributes: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source: str = "system"
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        rel_type = (
            self.relation_type.value
            if isinstance(self.relation_type, Enum)
            else self.relation_type
        )
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": rel_type,
            "attributes": dict(self.attributes),
            "confidence": self.confidence,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Relation:
        rel_val: RelationType | str = data.get(
            "relation_type", RelationType.CONNECTED_TO
        )
        try:
            rel_val = RelationType(rel_val)
        except ValueError:
            pass

        created_at = (
            datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else _utcnow()
        )
        updated_at = (
            datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else _utcnow()
        )

        return cls(
            id=data["id"],
            source_id=data["source_id"],
            target_id=data["target_id"],
            relation_type=rel_val,
            attributes=dict(data.get("attributes", {})),
            confidence=float(data.get("confidence", 1.0)),
            source=str(data.get("source", "system")),
            created_at=created_at,
            updated_at=updated_at,
        )
