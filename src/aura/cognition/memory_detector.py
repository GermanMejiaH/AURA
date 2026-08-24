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

    # Matches optional preambles (ahora, bueno, oye, mira, por favor, hey, hola, aura)
    # followed by an explicit imperative directive verb.
    DIRECTIVE_PATTERN = re.compile(
        r"^(?:(?:ahora|bueno|oye|mira|por\s+favor|hey|hola|aura)[,\s]*)*"
        r"(quiero\s+que\s+recuerdes|recuerda|guarda|no\s+olvides)\s+(?:que\s+)?(.+)$",
        flags=re.IGNORECASE,
    )

    @classmethod
    def _normalize_predicate(cls, raw_key: str) -> str:
        from ..memory.canonicalization import canonicalize_key

        return canonicalize_key(raw_key)

    @classmethod
    def detect(cls, input_text: str) -> ExplicitMemoryDirective:
        cleaned = input_text.strip().rstrip(".")
        cleaned_lower = cleaned.lower()

        # 1. Reject questions / inquiry statements (e.g. ¿recuerdas?, ¿cuál es?)
        if (
            "?" in input_text
            or "¿" in input_text
            or re.search(r"\brecuerdas\b", cleaned_lower)
            or re.search(r"\bsabes\s+si\b", cleaned_lower)
            or re.search(r"\bme\s+gustaria\b", cleaned_lower)
        ):
            return ExplicitMemoryDirective(detected=False)

        # 2. Reject negative recollections or personal statements without imperative command
        if re.search(r"\bno\s+recuerdo\b", cleaned_lower) or re.search(
            r"\bno\s+me\s+acuerdo\b", cleaned_lower
        ):
            return ExplicitMemoryDirective(detected=False)

        if re.search(r"^\s*recuerdo\b", cleaned_lower):
            return ExplicitMemoryDirective(detected=False)

        # 3. Match explicit directive pattern or update statement
        extracted_body: str | None = None
        match = cls.DIRECTIVE_PATTERN.search(cleaned)
        if match:
            extracted_body = match.group(2).strip()
        else:
            # Check for direct update statement: "(ahora|actualmente...) mi <key> es <val>"
            update_match = re.match(
                r"^(?:(?:ahora|bueno|oye|mira|por\s+favor|hey|hola|aura)[,\s]*)*"
                r"(?:mi|mis)\s+([\w\s]+?)\s+es\s+(.+)$",
                cleaned,
                flags=re.IGNORECASE,
            )
            if update_match:
                raw_k = update_match.group(1).strip()
                v_val = update_match.group(2).strip()
                extracted_body = f"mi {raw_k} es {v_val}"

        # 3B. Direct natural declarations without imperative prefix ("Recuerda que...")
        if not extracted_body:
            # A. Age: "Tengo 26 años" / "Tengo la edad de 26 años"
            m_age = re.match(
                r"^(?:(?:ahora|bueno|oye|mira|por\s+favor|hey|hola|aura)[,\s]*)*"
                r"(?:tengo|cumplí|cumpli)\s+(?:la\s+edad\s+de\s+)?(\d{1,3})\s+años$",
                cleaned,
                flags=re.IGNORECASE,
            )
            if m_age:
                val_age = m_age.group(1).strip()
                return ExplicitMemoryDirective(
                    detected=True,
                    subject="usuario",
                    predicate="edad",
                    object_val=val_age,
                    raw_statement=cleaned,
                    confirmation_response=f"Claro, he registrado que tienes {val_age} años.",
                )

            # B. Location / City: "Vivo en Medellín" / "Resido en Medellín"
            m_loc = re.match(
                r"^(?:(?:ahora|bueno|oye|mira|por\s+favor|hey|hola|aura)[,\s]*)*"
                r"(?:vivo|resido)\s+en\s+(.+)$",
                cleaned,
                flags=re.IGNORECASE,
            )
            if m_loc:
                val_loc = m_loc.group(1).strip()
                return ExplicitMemoryDirective(
                    detected=True,
                    subject="usuario",
                    predicate="ciudad",
                    object_val=val_loc,
                    raw_statement=cleaned,
                    confirmation_response=f"Entendido, he registrado que vives en {val_loc}.",
                )

            # C. Studies / Activity: "Estudio ingeniería de software" / "Estoy estudiando..."
            m_study = re.match(
                r"^(?:(?:ahora|bueno|oye|mira|por\s+favor|hey|hola|aura)[,\s]*)*"
                r"(?:estudio|estoy\s+estudiando)\s+(.+)$",
                cleaned,
                flags=re.IGNORECASE,
            )
            if m_study:
                val_st = m_study.group(1).strip()
                val_final = (
                    f"estudiando {val_st}" if not val_st.startswith("estudiando") else val_st
                )
                return ExplicitMemoryDirective(
                    detected=True,
                    subject="usuario",
                    predicate="actividad",
                    object_val=val_final,
                    raw_statement=cleaned,
                    confirmation_response=f"Claro, recordaré que estás {val_final}.",
                )

            # D. Occupation: "Trabajo como desarrollador"
            m_job = re.match(
                r"^(?:(?:ahora|bueno|oye|mira|por\s+favor|hey|hola|aura)[,\s]*)*"
                r"trabajo\s+como\s+(.+)$",
                cleaned,
                flags=re.IGNORECASE,
            )
            if m_job:
                val_job = m_job.group(1).strip()
                return ExplicitMemoryDirective(
                    detected=True,
                    subject="usuario",
                    predicate="ocupacion",
                    object_val=val_job,
                    raw_statement=cleaned,
                    confirmation_response=f"Claro, recordaré que trabajas como {val_job}.",
                )

            # E. Employer: "Trabajo en Empresa X" / "Trabajo en Google"
            m_emp = re.match(
                r"^(?:(?:ahora|bueno|oye|mira|por\s+favor|hey|hola|aura)[,\s]*)*"
                r"trabajo\s+en\s+(.+)$",
                cleaned,
                flags=re.IGNORECASE,
            )
            if m_emp:
                val_emp = m_emp.group(1).strip()
                return ExplicitMemoryDirective(
                    detected=True,
                    subject="usuario",
                    predicate="empleador",
                    object_val=val_emp,
                    raw_statement=cleaned,
                    confirmation_response=f"Claro, recordaré que trabajas en {val_emp}.",
                )

            # F. Name: "Soy Andrés" / "Me llamo Andrés"
            m_name = re.match(
                r"^(?:(?:ahora|bueno|oye|mira|por\s+favor|hey|hola|aura)[,\s]*)*"
                r"(?:soy|me\s+llamo)\s+([a-zA-ZáéíóúñÁÉÍÓÚÑ\s]+)$",
                cleaned,
                flags=re.IGNORECASE,
            )
            if m_name:
                val_name = m_name.group(1).strip()
                val_lower = val_name.lower()
                if not val_lower.startswith("de ") and not val_lower.startswith("un "):
                    return ExplicitMemoryDirective(
                        detected=True,
                        subject="usuario",
                        predicate="nombre",
                        object_val=val_name,
                        raw_statement=cleaned,
                        confirmation_response=f"Hola {val_name}, he registrado tu nombre.",
                    )

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
                m_key = re.match(
                    r"^(?:ahora\s+|actualmente\s+)?mi\s+([\w\s]+?)\s+es\s+",
                    first_part,
                    flags=re.IGNORECASE,
                )
                if m_key:
                    raw_k = m_key.group(1).strip()
                    k_clean = cls._normalize_predicate(raw_k)
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
        # A. "(ahora | actualmente)? mi <key> es <val>"
        match_mi = re.match(
            r"^(?:ahora\s+|actualmente\s+|hoy\s+)?mi\s+([\w\s]+?)\s+es\s+(.+)$",
            extracted_body,
            flags=re.IGNORECASE,
        )
        if match_mi:
            raw_key = match_mi.group(1).strip()
            val = match_mi.group(2).strip()
            key_clean = cls._normalize_predicate(raw_key)
            raw_k_display = raw_key.replace("ahora", "").replace("actualmente", "").strip()
            return ExplicitMemoryDirective(
                detected=True,
                subject="usuario",
                predicate=key_clean,
                object_val=val,
                raw_statement=cleaned,
                confirmation_response=f"Claro, recordaré que tu {raw_k_display} es {val}.",
            )

        # B. "estudio <action>" or "estoy <action>"
        match_estudio = re.match(r"^(?:estudio|estoy)\s+(.+)$", extracted_body, flags=re.IGNORECASE)
        if match_estudio:
            val = match_estudio.group(1).strip()
            val_final = f"estudiando {val}" if not val.startswith("estudiando") else val
            return ExplicitMemoryDirective(
                detected=True,
                subject="usuario",
                predicate="actividad",
                object_val=val_final,
                raw_statement=cleaned,
                confirmation_response=f"Claro, recordaré que estás {val_final}.",
            )

        # C. Fallback for general explicit facts
        return ExplicitMemoryDirective(
            detected=True,
            subject="usuario",
            predicate="dato",
            object_val=extracted_body,
            raw_statement=cleaned,
            confirmation_response=f"Claro, lo recordaré: '{extracted_body}'.",
        )
