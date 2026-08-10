from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ExplicitMemoryDirective:
    """Represents a detected unambiguous explicit memory directive from the user."""

    detected: bool
    subject: str = "usuario"
    predicate: str = ""
    object_val: str = ""
    raw_statement: str = ""
    confirmation_response: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


class ExplicitMemoryDetector:
    """Detects unambiguous memory commands in user utterances."""

    UNAMBIGUOUS_PATTERNS = (
        r"^(?:aura,?\s*)?(?:quiero que recuerdes|recuerda|guarda|no olvides)\s+que\s+(.+)$",
        r"^(?:aura,?\s*)?(?:quiero que recuerdes|recuerda|guarda|no olvides)\s+(.+)$",
    )

    @classmethod
    def detect(cls, input_text: str) -> ExplicitMemoryDirective:
        cleaned = input_text.strip()
        cleaned_lower = cleaned.lower()

        extracted_body: str | None = None
        for pattern in cls.UNAMBIGUOUS_PATTERNS:
            match = re.search(pattern, cleaned_lower, flags=re.IGNORECASE)
            if match:
                extracted_body = match.group(1).strip()
                break

        if not extracted_body:
            return ExplicitMemoryDirective(detected=False)

        # Parse extracted body for structured subject/predicate/object
        # 1. "mi <key> es <val>"
        match_mi = re.match(r"^mi\s+([\w\s]+?)\s+es\s+(.+)$", extracted_body, flags=re.IGNORECASE)
        if match_mi:
            raw_key = match_mi.group(1).strip()
            val = match_mi.group(2).strip()
            key_clean = raw_key.replace(" ", "_")
            return ExplicitMemoryDirective(
                detected=True,
                subject="usuario",
                predicate=key_clean,
                object_val=val,
                raw_statement=cleaned,
                confirmation_response=f"Claro, recordaré que tu {raw_key} es {val}.",
            )

        # 2. "estoy <verb/action>"
        match_estoy = re.match(r"^estoy\s+(.+)$", extracted_body, flags=re.IGNORECASE)
        if match_estoy:
            val = match_estoy.group(1).strip()
            return ExplicitMemoryDirective(
                detected=True,
                subject="usuario",
                predicate="actividad",
                object_val=f"estudiando {val}" if not val.startswith("estudiando") else val,
                raw_statement=cleaned,
                confirmation_response=f"Claro, recordaré que estás {val}.",
            )

        # 3. Fallback for general explicit facts
        return ExplicitMemoryDirective(
            detected=True,
            subject="usuario",
            predicate="dato",
            object_val=extracted_body,
            raw_statement=cleaned,
            confirmation_response=f"Claro, lo recordaré: '{extracted_body}'.",
        )
