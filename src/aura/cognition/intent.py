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


class ControlIntentDetector:
    """Deterministic pre-LLM detector for system control intents (EXIT, CANCEL)."""

    EXIT_VARIANTS: tuple[str, ...] = (
        "salir",
        "salí",
        "sali",
        "salís",
        "salis",
        "salid",
        "salida",
        "exit",
        "adios",
        "adiós",
        "chao",
        "chau",
        "bye",
        "cerrar",
        "cierra",
        "cierre",
        "cerrar sesión",
        "cerrar sesion",
        "cierra la sesión",
        "cierra la sesion",
        "apágate",
        "apagate",
        "apaga",
        "apagar",
        "termina",
        "terminar",
        "finalizar",
        "hasta luego",
        "nos vemos",
        "desactivar modo autónomo",
        "desactivar modo autonomo",
        "detener autónomo",
        "detener autonomo",
    )

    CANCEL_VARIANTS: tuple[str, ...] = (
        "cancela",
        "cancelar",
        "detener",
        "stop",
        "abortar",
        "para",
    )

    GREETING_VARIANTS: tuple[str, ...] = (
        "hola",
        "hola aura",
        "hey",
        "hey aura",
        "buenos dias",
        "buenos días",
        "buenas tardes",
        "buenas noches",
        "que tal",
        "qué tal",
        "hola ahora",
    )

    DIRECT_MEMORY_PATTERNS: tuple[str, ...] = (
        r"\bcu[aá]l\s+es\s+mi\b",
        r"\bc[oó]mo\s+me\s+llamo\b",
        r"\bqui[eé]n\s+soy\b",
        r"\bqu[eé]\s+sabes\s+(?:de|sobre)\s+m[ií]\b",
        r"\bsabes\s+cu[aá]l\s+es\s+mi\b",
        r"\bh[aá]blame\s+de\s+m[ií]\b",
        r"\bqu[eé]\s+recuerdas\s+de\s+m[ií]\b",
        # AGE
        r"\bcu[aá]ntos\s+a[nñ]os\s+tengo\b",
        r"\bqu[eé]\s+edad\s+tengo\b",
        r"\bdime\s+mi\s+edad\b",
        r"\brecuerdas\s+mi\s+edad\b",
        # LOCATION
        r"\bd[oó]nde\s+vivo\b",
        r"\ben\s+qu[eé]\s+ciudad\s+vivo\b",
        r"\brecuerdas\s+d[oó]nde\s+vivo\b",
        # STUDIES
        r"\bqu[eé]\s+(?:estudio|estudi[eé]|estoy\s+estudiando)\b",
        r"\brecuerdas\s+qu[eé]\s+estudio\b",
        # WORK
        r"\bd[oó]nde\s+trabajo\b",
        r"\ben\s+qu[eé]\s+trabajo\b",
        r"\bcu[aá]l\s+es\s+mi\s+ocupaci[oó]n\b",
        r"\ba\s+qu[eé]\s+me\s+dedico\b",
    )

    @classmethod
    def normalize_text(cls, text: str | Any) -> str:
        """Strips punctuation, symbols, normalizes accents, collapses whitespace,
        and normalizes Whisper STT variants."""
        if not text or not isinstance(text, str):
            return ""
        # Preserve % sign and math operators as words before removing punctuation
        t = text.replace("%", " por ciento ").replace("^", " elevado a ").replace("**", " elevado a ")
        # Remove common punctuation symbols
        cleaned = re.sub(r"[^\w\sáéíóúñÁÉÍÓÚÑ]", " ", t.strip().lower())
        # Translate accents to plain vowels
        unaccented = cleaned.translate(str.maketrans("áéíóú", "aeiou"))
        # Collapse multiple spaces into single space
        norm = re.sub(r"\s+", " ", unaccented).strip()

        # STT Whisper phonetic normalization rules
        norm = re.sub(r"\bdon\s+de\b", "donde", norm)
        norm = re.sub(r"\banios\b", "anos", norm)
        norm = re.sub(r"\bkien\b", "quien", norm)
        norm = re.sub(r"\bsoi\b", "soy", norm)
        norm = re.sub(r"\byamo\b", "llamo", norm)
        return norm

    @classmethod
    def is_exit(cls, input_text: str) -> bool:
        """Determines pre-LLM whether user input is an explicit EXIT command."""
        norm = cls.normalize_text(input_text)
        if not norm:
            return False

        # Strip optional leading/trailing "aura" keyword (e.g. "aura salir", "salir aura")
        words = norm.split()
        filtered_words = [w for w in words if w != "aura"]
        filtered_norm = " ".join(filtered_words)

        if not filtered_norm:
            return False

        # Direct match against normalized string or single word matching
        for variant in cls.EXIT_VARIANTS:
            norm_variant = cls.normalize_text(variant)
            if filtered_norm == norm_variant or norm == norm_variant:
                return True
            # Also check if filtered_norm is a 1-3 word utterance containing variant
            if len(filtered_words) <= 3 and norm_variant in filtered_norm:
                return True

        if re.search(
            r"\b(?:sali|salis|salir|salid|salida|cerrar|cierra|cierre|apaga|apagate|apagar|termina|terminar|finalizar|exit|adios|chau|chao|bye)\b",
            filtered_norm,
        ):
            return True

        return False

    @classmethod
    def is_cancel(cls, input_text: str) -> bool:
        """Determines pre-LLM whether user input is an explicit CANCEL command."""
        norm = cls.normalize_text(input_text)
        if not norm:
            return False

        words = [w for w in norm.split() if w != "aura"]
        filtered_norm = " ".join(words)

        for variant in cls.CANCEL_VARIANTS:
            norm_variant = cls.normalize_text(variant)
            if filtered_norm == norm_variant or norm == norm_variant:
                return True

        return False

    @classmethod
    def is_greeting(cls, input_text: str) -> bool:
        """Determines pre-LLM whether user input is a standard greeting."""
        norm = cls.normalize_text(input_text)
        if not norm:
            return False

        greeting_patterns = (
            r"\bhola\b",
            r"\bbuenos\s+d[ií]as\b",
            r"\bbuenas\s+tardes\b",
            r"\bbuenas\s+noches\b",
            r"\bc[oó]mo\s+est[aá]s\b",
            r"\bque\s+tal\b",
            r"\bqu[eé]\s+tal\b",
            r"\bhey\b",
            r"\bsaludos\b",
        )
        return any(re.search(p, norm, re.IGNORECASE) for p in greeting_patterns)

    @classmethod
    def get_greeting_response(cls) -> str:
        """Returns deterministic friendly greeting response."""
        return "¡Hola! Estoy muy bien, gracias por preguntar. ¿En qué puedo ayudarte hoy?"

    @classmethod
    def is_direct_memory_query(cls, input_text: str) -> bool:
        """Determines pre-LLM whether user input is a direct personal memory query."""
        norm = cls.normalize_text(input_text)
        if not norm:
            return False

        for pattern in cls.DIRECT_MEMORY_PATTERNS:
            if re.search(pattern, norm, re.IGNORECASE):
                return True

        return False

    @classmethod
    def is_time_query(cls, input_text: str) -> bool:
        """Determines pre-LLM whether user input is a query for current time or date."""
        norm = cls.normalize_text(input_text)
        if not norm:
            return False
        patterns = (
            r"\bque\s+hora\s+es\b",
            r"\bhora\s+actual\b",
            r"\bdime\s+la\s+hora\b",
            r"\bque\s+dia\s+es\b",
            r"\bque\s+d[ií]a\s+es\b",
            r"\bfecha\s+actual\b",
            r"\bque\s+fecha\s+es\b",
            r"\bdime\s+el\s+d[ií]a\b",
            r"\bdia\s+actual\b",
        )
        return any(re.search(p, norm, re.IGNORECASE) for p in patterns)

    @classmethod
    def get_time_response(cls, input_text: str) -> str:
        """Generates direct deterministic time or date response."""
        from datetime import datetime

        now = datetime.now()
        norm = cls.normalize_text(input_text)
        if any(w in norm for w in ("dia", "fecha")):
            days = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
            months = (
                "enero",
                "febrero",
                "marzo",
                "abril",
                "mayo",
                "junio",
                "julio",
                "agosto",
                "septiembre",
                "octubre",
                "noviembre",
                "diciembre",
            )
            day_name = days[now.weekday()]
            month_name = months[now.month - 1]
            return f"Hoy es {day_name}, {now.day} de {month_name} de {now.year}."
        else:
            time_str = now.strftime("%I:%M %p").lstrip("0")
            return f"Son las {time_str}."

    @classmethod
    def is_calculator_query(cls, input_text: str) -> bool:
        """Determines pre-LLM whether user input is a math query (arithmetic, roots, %, powers, trig, log)."""
        norm = cls.normalize_text(input_text)
        if not norm:
            return False
        patterns = (
            r"\bcuanto\s+es\s+\d+(?:\.\d+)?\s*(?:mas|\+|\-|menos|por|x|\*|entre|\/|dividido)\s*\d+(?:\.\d+)?\b",
            r"\b(?:multiplica|divide|suma|resta)\s+\d+(?:\.\d+)?\s+(?:por|entre|mas|menos|a)?\s*\d+(?:\.\d+)?\b",
            r"^\d+(?:\.\d+)?\s*(?:x|\*|por|\+|\-|entre|\/|dividido)\s*\d+(?:\.\d+)?$",
            r"\bra[íi]z\s+(?:cuadrada\s+)?de\s+\d+(?:\.\d+)?\b",
            r"\bsqrt\s*\(?\s*\d+(?:\.\d+)?\s*\)?\b",
            r"\b\d+(?:\.\d+)?\s*(?:%|por\s+ciento)\s+de\s+\d+(?:\.\d+)?\b",
            r"\bcuanto\s+es\s+el\s+\d+(?:\.\d+)?\s*(?:%|por\s+ciento)\s+de\s+\d+(?:\.\d+)?\b",
            r"\bpotencia\s+de\s+\d+(?:\.\d+)?\b",
            r"\b\d+(?:\.\d+)?\s+elevado\s+(?:a|a\s+la)?\s*\d+(?:\.\d+)?\b",
            r"\b\d+(?:\.\d+)?\s*(?:\^|\*\*)\s*\d+(?:\.\d+)?\b",
            r"\b(?:seno|coseno|tangente|sen|cos|tan)\s+(?:de\s+)?\d+(?:\.\d+)?\b",
            r"\blogaritmo\s+(?:natural\s+)?(?:de\s+)?\d+(?:\.\d+)?\b",
            r"\b(?:log|ln)\(\s*\d+(?:\.\d+)?\s*\)",
        )
        return any(re.search(p, norm, re.IGNORECASE) for p in patterns)

    @classmethod
    def get_calculator_response(cls, input_text: str) -> str:
        """Evaluates arithmetic, percentages, roots, powers, trig, and logs safely without LLM."""
        import math

        norm = cls.normalize_text(input_text)

        # 1. Square root check: "raíz cuadrada de 81", "raiz de 81", "sqrt(81)"
        sqrt_match = re.search(r"(?:raiz\s+(?:cuadrada\s+)?de\s+|sqrt\s*\(?\s*)(\d+(?:\.\d+)?)", norm, re.IGNORECASE)
        if sqrt_match:
            val = float(sqrt_match.group(1))
            res = math.sqrt(val)
            res_str = f"{res:.4f}".rstrip("0").rstrip(".")
            val_disp = int(val) if val.is_integer() else val
            return f"La raíz cuadrada de {val_disp} es {res_str}."

        # 2. Power check: "2 elevado a 8", "potencia de 2 a la 8", "2^8", "2**8"
        pow_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:elevado\s+(?:a|a\s+la)?|\^|\*\*)\s*(\d+(?:\.\d+)?)", norm, re.IGNORECASE)
        if not pow_match:
            pow_match = re.search(r"potencia\s+de\s+(\d+(?:\.\d+)?)\s+(?:a|elevado\s+a)?\s*(\d+(?:\.\d+)?)", norm, re.IGNORECASE)
        if pow_match:
            base_val = float(pow_match.group(1))
            exp_val = float(pow_match.group(2))
            res = math.pow(base_val, exp_val)
            res_str = f"{res:.4f}".rstrip("0").rstrip(".")
            b_disp = int(base_val) if base_val.is_integer() else base_val
            e_disp = int(exp_val) if exp_val.is_integer() else exp_val
            return f"{b_disp} elevado a {e_disp} es {res_str}."

        # 3. Trigonometry check: "seno de 30", "coseno de 45", "tangente de 60", "sen(30)"
        trig_match = re.search(r"(seno|coseno|tangente|sen|cos|tan)\s+(?:de\s+|\(\s*)?(\d+(?:\.\d+)?)", norm, re.IGNORECASE)
        if trig_match:
            func = trig_match.group(1).lower()
            deg = float(trig_match.group(2))
            rad = math.radians(deg)
            if func in ("seno", "sen"):
                res = math.sin(rad)
                fname = "seno"
            elif func in ("coseno", "cos"):
                res = math.cos(rad)
                fname = "coseno"
            else:
                res = math.tan(rad)
                fname = "tangente"
            res_str = f"{res:.4f}".rstrip("0").rstrip(".")
            deg_disp = int(deg) if deg.is_integer() else deg
            return f"El {fname} de {deg_disp} grados es {res_str}."

        # 4. Logarithm check: "logaritmo de 100", "logaritmo natural de 10", "log(100)", "ln(10)"
        log_match = re.search(r"(logaritmo\s+natural|logaritmo|log|ln)\s+(?:de\s+|\(\s*)?(\d+(?:\.\d+)?)", norm, re.IGNORECASE)
        if log_match:
            ltype = log_match.group(1).lower()
            val = float(log_match.group(2))
            if val <= 0:
                return "El logaritmo solo está definido para números positivos."
            if "natural" in ltype or ltype == "ln":
                res = math.log(val)
                lname = "logaritmo natural"
            else:
                res = math.log10(val)
                lname = "logaritmo en base 10"
            res_str = f"{res:.4f}".rstrip("0").rstrip(".")
            val_disp = int(val) if val.is_integer() else val
            return f"El {lname} de {val_disp} es {res_str}."

        # 5. Percentage check (e.g., "15% de 200" or "15 por ciento de 200")
        pct_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|por\s+ciento)\s+de\s+(\d+(?:\.\d+)?)", norm, re.IGNORECASE)
        if pct_match:
            pct_val = float(pct_match.group(1))
            total_val = float(pct_match.group(2))
            res = (pct_val / 100.0) * total_val
            res_str = f"{res:.2f}".rstrip("0").rstrip(".")
            p_disp = int(pct_val) if pct_val.is_integer() else pct_val
            t_disp = int(total_val) if total_val.is_integer() else total_val
            return f"El {p_disp}% de {t_disp} es {res_str}."

        # 6. Standard arithmetic operations
        match = re.search(
            r"(\d+(?:\.\d+)?)\s*(mas|\+|\-|menos|por|x|\*|entre|\/|dividido)\s*(\d+(?:\.\d+)?)", norm, re.IGNORECASE
        )
        if not match:
            match = re.search(
                r"(?:multiplica|divide)\s+(\d+(?:\.\d+)?)\s+(?:por|entre|dividido)\s+(\d+(?:\.\d+)?)", norm, re.IGNORECASE
            )
            if not match:
                return "No pude realizar ese cálculo."
            a_val = float(match.group(1))
            b_val = float(match.group(2))
            op = "por" if "multiplica" in norm else "entre"
        else:
            a_val = float(match.group(1))
            op = match.group(2)
            b_val = float(match.group(3))

        a_disp = int(a_val) if a_val.is_integer() else a_val
        b_disp = int(b_val) if b_val.is_integer() else b_val

        if op in ("mas", "+"):
            res = a_val + b_val
            r_disp = int(res) if res.is_integer() else f"{res:.2f}".rstrip("0").rstrip(".")
            return f"{a_disp} más {b_disp} es {r_disp}."
        elif op in ("menos", "-"):
            res = a_val - b_val
            r_disp = int(res) if res.is_integer() else f"{res:.2f}".rstrip("0").rstrip(".")
            return f"{a_disp} menos {b_disp} es {r_disp}."
        elif op in ("por", "x", "*"):
            res = a_val * b_val
            r_disp = int(res) if res.is_integer() else f"{res:.2f}".rstrip("0").rstrip(".")
            return f"{a_disp} por {b_disp} es {r_disp}."
        elif op in ("entre", "/", "dividido"):
            if b_val == 0:
                return "No se puede dividir entre cero."
            res_val = a_val / b_val
            res_str = f"{res_val:.2f}".rstrip("0").rstrip(".")
            return f"{a_disp} entre {b_disp} es {res_str}."

        return "No pude calcular ese resultado."

    @classmethod
    def is_reminder_query(cls, input_text: str) -> bool:
        """Determines pre-LLM whether user input is a reminder creation request."""
        norm = cls.normalize_text(input_text)
        if not norm:
            return False
        patterns = (
            r"\brecuerdame\b",
            r"\bagrega\s+un\s+recordatorio\b",
            r"\bpon\s+un\s+recordatorio\b",
            r"\bpon\s+una\s+alarma\b",
            r"\bcrea\s+un\s+recordatorio\b",
        )
        return any(re.search(p, norm) for p in patterns)

    @classmethod
    def is_reminder_list_query(cls, input_text: str) -> bool:
        """Determines pre-LLM whether user input requests a list of current reminders."""
        norm = cls.normalize_text(input_text)
        if not norm:
            return False
        patterns = (
            r"\bque\s+recordatorios?\s+(?:tengo|hay)\b",
            r"\blista\s+(?:mis\s+)?recordatorios?\b",
            r"\btengo\s+(?:algun|alguna|algún)\s+(?:recordatorio|alarma)\b",
            r"\bver\s+recordatorios?\b",
            r"\bmostrar\s+recordatorios?\b",
        )
        return any(re.search(p, norm) for p in patterns)

    @classmethod
    def parse_reminder_query(cls, input_text: str) -> tuple[str, float]:
        """Parses reminder text description and delay in seconds."""
        norm = cls.normalize_text(input_text)
        delay = 60.0

        sec_match = re.search(r"en\s+(\d+)\s+segundo", norm)
        min_match = re.search(r"en\s+(\d+)\s+minuto", norm)
        hr_match = re.search(r"en\s+(\d+)\s+hora", norm)

        if sec_match:
            delay = float(sec_match.group(1))
        elif min_match:
            delay = float(min_match.group(1)) * 60.0
        elif hr_match:
            delay = float(hr_match.group(1)) * 3600.0

        clean_pat = (
            r"^(?:aura\s+)?(?:recuerdame|agrega\s+un\s+recordatorio|pon\s+un\s+recordatorio|"
            r"pon\s+una\s+alarma|crea\s+un\s+recordatorio)\s+(?:que\s+)?(?:de\s+)?"
        )
        desc = re.sub(clean_pat, "", norm, flags=re.IGNORECASE)
        desc = re.sub(r"\s+en\s+\d+\s+(?:segundo|minuto|hora)s?$", "", desc, flags=re.IGNORECASE)
        if not desc.strip():
            desc = "recordatorio de voz"

        return (desc.strip(), delay)

    @classmethod
    def is_user_profile_query(cls, input_text: str) -> bool:
        """Determines pre-LLM whether user input is a user profile query."""
        norm = cls.normalize_text(input_text)
        if not norm:
            return False
        patterns = (
            r"\bquien\s+soy\b",
            r"\bcual\s+es\s+mi\s+nombre\b",
            r"\bcomo\s+me\s+llamo\b",
            r"\bdonde\s+vivo\b",
            r"\bcuantos\s+anos\s+tengo\b",
            r"\bque\s+sabes\s+de\s+mi\b",
        )
        return any(re.search(p, norm) for p in patterns)

    @classmethod
    def is_weather_query(cls, input_text: str) -> bool:
        """Determines pre-LLM whether user input is a weather query."""
        norm = cls.normalize_text(input_text)
        if not norm:
            return False
        patterns = (
            r"\bclima\b",
            r"\btemperatura\b",
            r"\bva\s+a\s+llover\b",
            r"\bque\s+clima\s+hace\b",
            r"\bcomo\s+esta\s+el\s+clima\b",
        )
        return any(re.search(p, norm) for p in patterns)

    @classmethod
    def get_weather_response(cls, input_text: str) -> str:
        """Generates concise deterministic weather response."""
        return "El clima actual está despejado con una temperatura agradable de 22 grados."


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
        r"\bqu[eé]\s+recuerdas\b",
        r"\bqu[eé]\s+sabes(?:\s+(?:de|sobre))?\b",
        r"\bqui[eé]n\s+soy\b",
        r"\bh[aá]blame\s+de\s+m[ií]\b",
        r"\bqu[eé]\s+conoces(?:\s+(?:de|sobre))?\b",
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
