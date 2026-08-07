from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .graph import CognitiveWorldModel
from .models import Entity, Relation


class CWMPersistenceProvider:
    """File-based JSON persistence provider for the Cognitive World Model graph."""

    def __init__(self, storage_path: str | os.PathLike[str] = "data/cwm_store.json") -> None:
        self.storage_path = Path(storage_path)

    def save(
        self,
        cwm: CognitiveWorldModel,
        filepath: str | os.PathLike[str] | None = None,
    ) -> Path:
        target_path = Path(filepath) if filepath is not None else self.storage_path
        target_path.parent.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {
            "version": "1.0.0",
            "entities": [e.to_dict() for e in cwm.all_entities()],
            "relations": [r.to_dict() for r in cwm.all_relations()],
        }

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return target_path

    def load(
        self,
        cwm: CognitiveWorldModel | None = None,
        filepath: str | os.PathLike[str] | None = None,
    ) -> CognitiveWorldModel:
        target_path = Path(filepath) if filepath is not None else self.storage_path
        model = cwm if cwm is not None else CognitiveWorldModel()

        if not target_path.exists():
            return model

        with open(target_path, encoding="utf-8") as f:
            data = json.load(f)

        entities_data = data.get("entities", [])
        relations_data = data.get("relations", [])

        for edata in entities_data:
            entity = Entity.from_dict(edata)
            model.add_entity(entity)

        for rdata in relations_data:
            relation = Relation.from_dict(rdata)
            model.add_relation(relation)

        return model
