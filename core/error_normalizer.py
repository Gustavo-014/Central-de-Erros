import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def _load_rules() -> Dict[str, Any]:
    """Carrega as regras de normalização a partir de um arquivo JSON."""
    rules_path = Path(__file__).resolve().parent.parent / "data" / "error_rules.json"

    with rules_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _normalize_text(value: str) -> str:
    """Normaliza o texto removendo espaços extras e pontuações de formatação."""
    normalized = re.sub(r"\s+", " ", value.strip())
    if normalized.endswith("."):
        normalized = normalized[:-1]
    return normalized


def normalize_error(error_original: str) -> Optional[str]:
    """Normaliza uma mensagem de erro original conforme as regras do arquivo JSON."""
    rules = _load_rules()

    if error_original is None:
        return None

    original_text = str(error_original).strip()
    if not original_text:
        return None

    if original_text in {item.strip() for item in rules.get("ignorar", [])}:
        return None

    if "/" in original_text:
        parts = [part.strip() for part in original_text.split("/") if part.strip()]
        if parts:
            original_text = parts[-1]

    for substitution in rules.get("substituicoes", []):
        contain_text = substitution.get("contem", "")
        result_text = substitution.get("resultado", "")
        if contain_text and contain_text in original_text:
            original_text = result_text
            break

    normalized_error = _normalize_text(original_text)

    if normalized_error in {item.strip() for item in rules.get("usar_ultimo_erro", [])}:
        if "/" in error_original:
            parts = [part.strip() for part in str(error_original).split("/") if part.strip()]
            if parts:
                normalized_error = _normalize_text(parts[-1])

    return normalized_error or None
