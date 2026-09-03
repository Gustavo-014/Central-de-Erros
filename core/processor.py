from typing import Any, Dict, List, Tuple

import pandas as pd

from core.error_normalizer import normalize_error
from core.extractor import extract_occurrence
from core.template_loader import load_templates


def process_dataframe(dataframe: pd.DataFrame) -> Tuple[Dict[str, Dict[str, List[Dict[str, str]]]], List[str]]:
    """Extrai, normaliza, agrupa e elimina duplicados a partir da planilha."""
    result: Dict[str, Dict[str, List[Dict[str, str]]]] = {}
    pending_errors: List[str] = []
    templates = load_templates()

    for row in dataframe.to_dict("records"):
        occurrence = extract_occurrence(row)
        cliente = occurrence.get("cliente") or ""
        erro_original = occurrence.get("erro_original") or ""
        erro_normalizado = normalize_error(erro_original)

        if erro_normalizado is None:
            continue

        if not cliente:
            continue

        if not any(value for value in occurrence.values() if value not in [None, ""] and value != cliente and value != erro_original):
            continue

        if cliente not in result:
            result[cliente] = {}

        if erro_normalizado not in result[cliente]:
            result[cliente][erro_normalizado] = []

        occurrence_key = tuple(sorted({key: value for key, value in occurrence.items() if value not in [None, ""] and key not in ["cliente", "erro_original"]}.items()))
        if not any(
            tuple(sorted({key: value for key, value in item.items() if value not in [None, ""] and key not in ["cliente", "erro_original"]}.items())) == occurrence_key
            for item in result[cliente][erro_normalizado]
        ):
            result[cliente][erro_normalizado].append(
                {key: value for key, value in occurrence.items() if value not in [None, ""] and key not in ["cliente", "erro_original"]}
            )

        if erro_normalizado not in templates:
            if erro_normalizado not in pending_errors:
                pending_errors.append(erro_normalizado)

    return (
        {
            cliente: {
                erro: result[cliente][erro]
                for erro in sorted(result[cliente])
            }
            for cliente in sorted(result)
        },
        pending_errors,
    )
