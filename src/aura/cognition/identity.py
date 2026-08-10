from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import ConfigurationManager


@dataclass
class AURAIdentity:
    """Represents AURA's core identity, mission, personality and behavioral guidelines."""

    name: str = "AURA"
    mission: str = "Asistir al usuario con precisión, empatía, seguridad y concisión."
    personality_style: str = "profesional, amable, claro y directo"
    language: str = "es"
    behavior_rules: list[str] = field(
        default_factory=lambda: [
            "Responder siempre en español de forma concisa (1 a 3 oraciones por voz).",
            "Ser respetuoso, claro y servicial en todo momento.",
            "Respetar la privacidad y las preferencias expresadas por el usuario.",
        ]
    )
    limitations: list[str] = field(
        default_factory=lambda: [
            "No puede realizar acciones físicas sin módulos robóticos o herramientas autorizadas.",
            "No debe inventar o alucinar datos personales que no estén en la memoria persistente.",
        ]
    )


class IdentityManager:
    """Manages AURA's identity configuration independently from user memory."""

    def __init__(self, config: ConfigurationManager | None = None) -> None:
        self.config = config
        self._lock = threading.RLock()
        self._identity = AURAIdentity()
        if self.config is not None:
            self.load_from_config()

    def load_from_config(self) -> None:
        with self._lock:
            if self.config is None:
                return

            name = self.config.get_typed("identity.name", str, "AURA")
            mission = self.config.get_typed(
                "identity.mission", str, self._identity.mission
            )
            personality = self.config.get_typed(
                "identity.personality_style", str, self._identity.personality_style
            )
            lang = self.config.get_typed("identity.language", str, "es")

            rules_raw = self.config.get("identity.behavior_rules", None)
            rules = (
                list(rules_raw)
                if isinstance(rules_raw, list)
                else self._identity.behavior_rules
            )

            limits_raw = self.config.get("identity.limitations", None)
            limits = (
                list(limits_raw)
                if isinstance(limits_raw, list)
                else self._identity.limitations
            )

            self._identity = AURAIdentity(
                name=name,
                mission=mission,
                personality_style=personality,
                language=lang,
                behavior_rules=rules,
                limitations=limits,
            )

    def get_identity(self) -> AURAIdentity:
        with self._lock:
            return AURAIdentity(
                name=self._identity.name,
                mission=self._identity.mission,
                personality_style=self._identity.personality_style,
                language=self._identity.language,
                behavior_rules=list(self._identity.behavior_rules),
                limitations=list(self._identity.limitations),
            )

    def update_identity(
        self,
        name: str | None = None,
        mission: str | None = None,
        personality_style: str | None = None,
        language: str | None = None,
        behavior_rules: list[str] | None = None,
        limitations: list[str] | None = None,
    ) -> AURAIdentity:
        with self._lock:
            if name is not None:
                self._identity.name = name
            if mission is not None:
                self._identity.mission = mission
            if personality_style is not None:
                self._identity.personality_style = personality_style
            if language is not None:
                self._identity.language = language
            if behavior_rules is not None:
                self._identity.behavior_rules = list(behavior_rules)
            if limitations is not None:
                self._identity.limitations = list(limitations)
            return self.get_identity()
