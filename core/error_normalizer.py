import json
import re
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


def normalize_error(error_original: str) -> Optional[str]:
    """Normaliza uma mensagem de erro original conforme as regras do arquivo JSON."""
    if error_original is None:
        return None

    rules = _load_rules()
    original_text = str(error_original).strip()
    if not original_text:
        return None

    cleaned_text = _normalize_text(original_text)

    if _normalize_for_compare(cleaned_text) in {
        _normalize_for_compare(item) for item in rules.get("ignorar", [])
    }:
        return None

    if any(
        _normalize_for_compare(item) in _normalize_for_compare(cleaned_text)
        for item in rules.get("ignorar_trechos", [])
    ):
        return None

    relevant_text = _split_by_separator(cleaned_text)

    for substitution in rules.get("substituicoes", []):
        source = substitution.get("de", "")
        target = substitution.get("para", "")
        if source and _normalize_for_compare(source) in _normalize_for_compare(relevant_text):
            relevant_text = target
            break

    for prefix_rule in rules.get("prefixos", []):
        prefix = prefix_rule.get("prefixo", "")
        result = prefix_rule.get("resultado", "")
        if prefix and _normalize_for_compare(relevant_text).startswith(_normalize_for_compare(prefix)):
            relevant_text = result
            break

    return _normalize_text(relevant_text) or None
