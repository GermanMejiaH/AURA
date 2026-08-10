from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class IntentType(Enum):
    GREETING = "greeting"
    FAREWELL = "farewell"
    QUESTION = "question"
    COMMAND = "command"
    INFORMATION_REQUEST = "information_request"
    MEMORY_QUERY = "memory_query"
    MEMORY_UPDATE = "memory_update"
    TASK_REQUEST = "task_request"
    CLARIFICATION = "clarification"
    CONFIRMATION = "confirmation"
    CANCELLATION = "cancellation"
    CASUAL_CONVERSATION = "casual_conversation"


@dataclass
class Intent:
    """Structured representation of detected user intent."""

    intent_type: IntentType
    confidence: float = 1.0
    parameters: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""


class IntentDetector:
    """Lightweight, deterministic regex/keyword intent detector with safe fallback."""

    # Explicit memory update pattern match
    MEMORY_UPDATE_PATTERNS = (
        r"\b(?:quiero\s+que\s+recuerdes|recuerda|guarda|no\s+olvides)\b",
        r"\bahora\s+mi\s+[\w\s]+\s+es\b",
        r"\bmi\s+[\w\s]+\s+ahora\s+es\b",
    )

    # Memory query patterns
    MEMORY_QUERY_PATTERNS = (
        r"\b(?:recuerdas|sabes)\s+cu[aá]l\b",
        r"\bcu[aá]l\s+es\s+mi\b",
        r"\bcu[aá]ndo\s+cumplo\b",
        r"\bqu[eé]\s+d[ií]a\s+cumplo\b",
        r"\brecuerdas\s+mi\b",
    )

    GREETING_PATTERNS = (
        r"^(?:hola|buenos\s+d[ií]as|buenas\s+tardes|buenas\s+noches|hey|saludos)\b",
        r"\bhola,?\s*(?:aura|laura)\b",
    )

    FAREWELL_PATTERNS = (r"^(?:adi[oó]s|chao|hasta\s+luego|nos\s+vemos|salir|bye|chao)\b",)

    CONFIRMATION_PATTERNS = (
        r"^(?:s[ií]|s[ií],\s+hazlo|claro|de\s+acuerdo|confirmar|acepto|de\s+una)\b",
    )

    CANCELLATION_PATTERNS = (r"^(?:cancela|cancelar|no,\s+cancela|detener|para|stop|abortar)\b",)

    TASK_PATTERNS = (r"^(?:busca|analiza|crea|organiza|programa|revisa|organizar)\b",)

    COMMAND_PATTERNS = (r"^(?:apaga|enciende|mueve|ejecuta|navega|reproduce)\b",)

    TOPIC_PATTERNS = (
        r"\b(?:hablemos|hablando|sobre|de|pensando\s+en|interesa)\s+([a-zA-ZáéíóúñÁÉÍÓÚÑ]{3,20})\b",
    )

    PERSONAL_INDICATORS = (
        r"\b(?:mi|mis|m[ií]o|m[ií]as|yo|tengo|llamo|llamaba|nombre|comida|perro|perra|mascota|casa|cumplea[ñn]os|gusto|favorit[oa]|estudi[oa]|estudiando|trabaj[oa]|trabajando|viv[oí]|vivir|preferencia|actividad)\b",
    )

    @classmethod
    def detect(cls, input_text: str) -> Intent:
        if not input_text or not input_text.strip():
            return Intent(
                intent_type=IntentType.CASUAL_CONVERSATION,
                confidence=1.0,
                raw_text=input_text,
            )

        text_clean = input_text.strip().lower()
        extracted_params: dict[str, Any] = {}

        # Topic extraction heuristic
        for topic_pat in cls.TOPIC_PATTERNS:
            match = re.search(topic_pat, text_clean, re.IGNORECASE)
            if match:
                extracted_params["topic"] = match.group(1).strip()
                break

        # 1. Check Explicit Memory Update
        for pat in cls.MEMORY_UPDATE_PATTERNS:
            if re.search(pat, text_clean, re.IGNORECASE):
                return Intent(
                    intent_type=IntentType.MEMORY_UPDATE,
                    confidence=0.95,
                    parameters=extracted_params,
                    raw_text=input_text,
                )

        # 2. Check Memory Query
        for pat in cls.MEMORY_QUERY_PATTERNS:
            if re.search(pat, text_clean, re.IGNORECASE):
                return Intent(
                    intent_type=IntentType.MEMORY_QUERY,
                    confidence=0.95,
                    parameters=extracted_params,
                    raw_text=input_text,
                )

        # 3. Check Greeting
        for pat in cls.GREETING_PATTERNS:
            if re.search(pat, text_clean, re.IGNORECASE):
                return Intent(
                    intent_type=IntentType.GREETING,
                    confidence=0.95,
                    parameters=extracted_params,
                    raw_text=input_text,
                )

        # 4. Check Farewell
        for pat in cls.FAREWELL_PATTERNS:
            if re.search(pat, text_clean, re.IGNORECASE):
                return Intent(
                    intent_type=IntentType.FAREWELL,
                    confidence=0.95,
                    parameters=extracted_params,
                    raw_text=input_text,
                )

        # 5. Check Confirmation
        for pat in cls.CONFIRMATION_PATTERNS:
            if re.search(pat, text_clean, re.IGNORECASE):
                return Intent(
                    intent_type=IntentType.CONFIRMATION,
                    confidence=0.90,
                    parameters=extracted_params,
                    raw_text=input_text,
                )

        # 6. Check Cancellation
        for pat in cls.CANCELLATION_PATTERNS:
            if re.search(pat, text_clean, re.IGNORECASE):
                return Intent(
                    intent_type=IntentType.CANCELLATION,
                    confidence=0.90,
                    parameters=extracted_params,
                    raw_text=input_text,
                )

        # 7. Check Task Request
        for pat in cls.TASK_PATTERNS:
            if re.search(pat, text_clean, re.IGNORECASE):
                extracted_params["task"] = text_clean
                return Intent(
                    intent_type=IntentType.TASK_REQUEST,
                    confidence=0.85,
                    parameters=extracted_params,
                    raw_text=input_text,
                )

        # 8. Check Command
        for pat in cls.COMMAND_PATTERNS:
            if re.search(pat, text_clean, re.IGNORECASE):
                extracted_params["command"] = text_clean
                return Intent(
                    intent_type=IntentType.COMMAND,
                    confidence=0.85,
                    parameters=extracted_params,
                    raw_text=input_text,
                )

        # 9. Check Question
        if text_clean.startswith("¿") or re.search(
            r"^(?:qu[eé]|c[oó]mo|cu[aá]ndo|d[oó]nde|por\s+qu[eé]|qui[eé]n|cu[aá]l|cu[aá]nto)\b",
            text_clean,
            re.IGNORECASE,
        ):
            return Intent(
                intent_type=IntentType.QUESTION,
                confidence=0.80,
                parameters=extracted_params,
                raw_text=input_text,
            )

        # Default safe fallback
        return Intent(
            intent_type=IntentType.CASUAL_CONVERSATION,
            confidence=0.70,
            parameters=extracted_params,
            raw_text=input_text,
        )

    @classmethod
    def should_query_persistent_memory(cls, intent: Intent, input_text: str) -> bool:
        """Determines intent-aware persistent memory retrieval policy."""
        # Never query SQLite for greetings, farewells, casual chat, confirmation, cancellation
        if intent.intent_type in (
            IntentType.GREETING,
            IntentType.FAREWELL,
            IntentType.CASUAL_CONVERSATION,
            IntentType.CONFIRMATION,
            IntentType.CANCELLATION,
        ):
            return False

        # Always query for explicit memory operations
        if intent.intent_type in (IntentType.MEMORY_QUERY, IntentType.MEMORY_UPDATE):
            return True

        # For Questions, Task requests, Commands: query if personal context indicators exist
        text_clean = input_text.strip().lower()
        for pat in cls.PERSONAL_INDICATORS:
            if re.search(pat, text_clean, re.IGNORECASE):
                return True

        # For questions starting with ¿cómo?, ¿quién?, ¿cuál?, ¿dónde?, ¿qué?: default query
        if intent.intent_type == IntentType.QUESTION and not re.search(
            r"\b(?:luz|gravedad|tierra|sol|luna|mapa|clima|tiempo|pa[ií]s)\b",
            text_clean,
        ):
            return True

        return False
