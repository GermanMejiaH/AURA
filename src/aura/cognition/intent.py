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
    )

    FAREWELL_PATTERNS = (
        r"^(?:adi[oó]s|chao|hasta\s+luego|nos\s+vemos|salir|bye|chao)\b",
    )

    CONFIRMATION_PATTERNS = (
        r"^(?:s[ií]|s[ií],\s+hazlo|claro|de\s+acuerdo|confirmar|acepto|de\s+una)\b",
    )

    CANCELLATION_PATTERNS = (
        r"^(?:cancela|cancelar|no,\s+cancela|detener|para|stop|abortar)\b",
    )

    TASK_PATTERNS = (
        r"^(?:busca|analiza|crea|organiza|programa|revisa)\b",
    )

    COMMAND_PATTERNS = (
        r"^(?:apaga|enciende|mueve|ejecuta|navega|reproduce)\b",
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

        # 1. Check Explicit Memory Update
        for pat in cls.MEMORY_UPDATE_PATTERNS:
            if re.search(pat, text_clean, re.IGNORECASE):
                return Intent(
                    intent_type=IntentType.MEMORY_UPDATE,
                    confidence=0.95,
                    raw_text=input_text,
                )

        # 2. Check Memory Query
        for pat in cls.MEMORY_QUERY_PATTERNS:
            if re.search(pat, text_clean, re.IGNORECASE):
                return Intent(
                    intent_type=IntentType.MEMORY_QUERY,
                    confidence=0.95,
                    raw_text=input_text,
                )

        # 3. Check Greeting
        for pat in cls.GREETING_PATTERNS:
            if re.search(pat, text_clean, re.IGNORECASE):
                return Intent(
                    intent_type=IntentType.GREETING,
                    confidence=0.95,
                    raw_text=input_text,
                )

        # 4. Check Farewell
        for pat in cls.FAREWELL_PATTERNS:
            if re.search(pat, text_clean, re.IGNORECASE):
                return Intent(
                    intent_type=IntentType.FAREWELL,
                    confidence=0.95,
                    raw_text=input_text,
                )

        # 5. Check Confirmation
        for pat in cls.CONFIRMATION_PATTERNS:
            if re.search(pat, text_clean, re.IGNORECASE):
                return Intent(
                    intent_type=IntentType.CONFIRMATION,
                    confidence=0.90,
                    raw_text=input_text,
                )

        # 6. Check Cancellation
        for pat in cls.CANCELLATION_PATTERNS:
            if re.search(pat, text_clean, re.IGNORECASE):
                return Intent(
                    intent_type=IntentType.CANCELLATION,
                    confidence=0.90,
                    raw_text=input_text,
                )

        # 7. Check Task Request
        for pat in cls.TASK_PATTERNS:
            if re.search(pat, text_clean, re.IGNORECASE):
                return Intent(
                    intent_type=IntentType.TASK_REQUEST,
                    confidence=0.85,
                    parameters={"task": text_clean},
                    raw_text=input_text,
                )

        # 8. Check Command
        for pat in cls.COMMAND_PATTERNS:
            if re.search(pat, text_clean, re.IGNORECASE):
                return Intent(
                    intent_type=IntentType.COMMAND,
                    confidence=0.85,
                    parameters={"command": text_clean},
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
                raw_text=input_text,
            )

        # Default safe fallback
        return Intent(
            intent_type=IntentType.CASUAL_CONVERSATION,
            confidence=0.70,
            raw_text=input_text,
        )
