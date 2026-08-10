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
        r"^(?:hola|buenas|hey|oye)?\s*(?:aura,?\s*)?"
        r"(?:quiero que recuerdes|recuerda|guarda|no olvides)\s+(?:que\s+)?(.+)$",
        r"^(?:aura,?\s*)?(?:quiero que recuerdes|recuerda|guarda|no olvides)\s+(?:que\s+)?(.+)$",
    )

    @classmethod
    def detect(cls, input_text: str) -> ExplicitMemoryDirective:
        cleaned = input_text.strip().rstrip(".")
        cleaned_lower = cleaned.lower()

        extracted_body: str | None = None
        for pattern in cls.UNAMBIGUOUS_PATTERNS:
            match = re.search(pattern, cleaned_lower, flags=re.IGNORECASE)
            if match:
                extracted_body = match.group(1).strip()
                break

        if not extracted_body:
            return ExplicitMemoryDirective(detected=False)

        # Handle self-correction phrases in single sentence: "..., digo no, el 2 de agosto"
        correction_patterns = [r",\s*digo\s+no,\s*", r",\s*no,\s*", r"\s+digo\s+no,\s*"]
        for c_pat in correction_patterns:
            if re.search(c_pat, extracted_body, flags=re.IGNORECASE):
                parts = re.split(c_pat, extracted_body, flags=re.IGNORECASE)
                first_part = parts[0].strip()
                last_part = parts[-1].strip()
                # Parse "mi <key> es" and apply last_part as val
                m_key = re.match(r"^mi\s+([\w\s]+?)\s+es\s+", first_part, flags=re.IGNORECASE)
                if m_key:
                    raw_k = m_key.group(1).strip()
                    k_clean = raw_k.replace(" ", "_")
                    val_clean = re.sub(r"^(?:el\s+)?", "", last_part, flags=re.IGNORECASE).strip()
                    val_final = f"el {val_clean}" if not last_part.startswith("el ") else last_part
                    confirm_msg = f"Claro, he registrado que tu {raw_k} es {val_final}."
                    return ExplicitMemoryDirective(
                        detected=True,
                        subject="usuario",
                        predicate=k_clean,
                        object_val=val_final,
                        raw_statement=cleaned,
                        confirmation_response=confirm_msg,
                    )

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
