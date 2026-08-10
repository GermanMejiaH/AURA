from __future__ import annotations

import re

# Dictionary mapping alias keys or variants to their canonical key
KNOWN_CANONICAL_MAP: dict[str, str] = {
    "comida_favorita_ahora": "comida_favorita",
    "comida_preferida": "comida_favorita",
    "mi_comida_favorita": "comida_favorita",
    "plato_favorito": "comida_favorita",
    "color_favorito_ahora": "color_favorito",
    "color_preferido": "color_favorito",
    "mi_color_favorito": "color_favorito",
    "pelicula_favorita_ahora": "pelicula_favorita",
    "pelicula_preferida": "pelicula_favorita",
    "mi_pelicula_favorita": "pelicula_favorita",
    "cumpleanos": "cumpleaños",
    "fecha_nacimiento": "fecha_de_nacimiento",
    "pais": "país",
}


def canonicalize_key(key: str) -> str:
    """Canonicalizes memory fact predicates and preference keys into standard form."""
    if not key:
        return ""

    raw_clean = key.lower().strip()
    # Check direct dictionary map first
    if raw_clean in KNOWN_CANONICAL_MAP:
        return KNOWN_CANONICAL_MAP[raw_clean]

    # Strip temporal adverbs (ahora, actualmente, hoy, hoy_en_dia, en_este_momento)
    k = re.sub(
        r"\b(ahora|actualmente|hoy|hoy_en_dia|en_este_momento|de_ahora_en_adelante)\b",
        "",
        raw_clean,
        flags=re.IGNORECASE,
    )

    # Strip leading possessives/articles (mi_, mis_, el_, la_, los_, las_)
    k = re.sub(r"^(?:mi|mis|el|la|los|las)[\s_]+", "", k, flags=re.IGNORECASE)

    # Normalize spaces and underscores
    k = k.strip().replace(" ", "_")
    k = re.sub(r"_+", "_", k).strip("_")

    # Check direct dictionary map again after normalization
    if k in KNOWN_CANONICAL_MAP:
        return KNOWN_CANONICAL_MAP[k]

    # Map suffix _preferido -> _favorito, _preferida -> _favorita
    if k.endswith("_preferido"):
        k = k[:-10] + "_favorito"
    elif k.endswith("_preferida"):
        k = k[:-10] + "_favorita"

    return k
