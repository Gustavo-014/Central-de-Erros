import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st

from core.utils import normalize_text as _normalize_text


@st.cache_data
def _load_rules() -> Dict[str, Any]:
    """Carrega as regras de normalização a partir de um arquivo JSON."""
    rules_path = Path(__file__).resolve().parent.parent / "data" / "error_rules.json"

    with rules_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _normalize_for_compare(value: str) -> str:
    """Normaliza textos para comparação sem diferenciar maiúsculas/minúsculas."""
    return _normalize_text(value).casefold()


@st.cache_data
def _load_compiled_rules() -> Dict[str, Any]:
    """Carrega e pré-compila as regras de normalização para buscas O(1) e comparações otimizadas."""
    raw_rules = _load_rules()
    return {
        "ignorar": {
            _normalize_for_compare(item) for item in raw_rules.get("ignorar", []) if item
        },
        "ignorar_trechos": [
            _normalize_for_compare(item) for item in raw_rules.get("ignorar_trechos", []) if item
        ],
        "substituicoes": [
            (_normalize_for_compare(s.get("de", "")), s.get("para", ""))
            for s in raw_rules.get("substituicoes", [])
            if s.get("de")
        ],
        "prefixos": [
            (_normalize_for_compare(p.get("prefixo", "")), p.get("resultado", ""))
            for p in raw_rules.get("prefixos", [])
            if p.get("prefixo")
        ],
    }


def _split_by_separator(value: str) -> str:
    """Resolve mensagens separadas por barra, utilizando o primeiro trecho relevante."""
    if "/" not in value:
        return value

    parts = [part.strip() for part in value.split("/") if part.strip()]
    if not parts:
        return value

    for part in reversed(parts):
        normalized_part = _normalize_for_compare(part)
        if normalized_part in {"erro captcha", "failed to get"}:
            continue
        return part
    return parts[-1]


@lru_cache(maxsize=4096)
def _normalize_error_cached(original_text: str) -> Optional[str]:
    """Lógica central de normalização com cache em memória (LRU) para repetições constantes."""
    cleaned_text = _normalize_text(original_text)
    compare_text = _normalize_for_compare(cleaned_text)

    rules = _load_compiled_rules()

    if compare_text in rules["ignorar"]:
        return None

    for item in rules["ignorar_trechos"]:
        if item in compare_text:
            return None

    relevant_text = _split_by_separator(cleaned_text)
    relevant_compare = _normalize_for_compare(relevant_text)

    for source_comp, target in rules["substituicoes"]:
        if source_comp in relevant_compare:
            relevant_text = target
            relevant_compare = _normalize_for_compare(relevant_text)
            break

    for prefix_comp, result in rules["prefixos"]:
        if relevant_compare.startswith(prefix_comp):
            relevant_text = result
            break

    return _normalize_text(relevant_text) or None


def normalize_error(error_original: str) -> Optional[str]:
    """Normaliza uma mensagem de erro original conforme as regras do arquivo JSON."""
    if error_original is None:
        return None

    original_text = str(error_original).strip()
    if not original_text:
        return None

    return _normalize_error_cached(original_text)
