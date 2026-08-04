from typing import Dict, Optional

import pandas as pd


def extract_occurrence(row: pd.Series) -> Dict[str, Optional[str]]:
    """Extrai os dados relevantes de uma linha da planilha para processamento posterior."""
    occurrence: Dict[str, Optional[str]] = {
        "cliente": None,
        "erro_original": None,
        "placa": None,
        "renavam": None,
        "cnpj": None,
    }

    cliente = row.get("Nome da Conta")
    if pd.notna(cliente):
        occurrence["cliente"] = str(cliente).strip()

    erro_original = row.get("Mensagem de Erro")
    if pd.notna(erro_original):
        occurrence["erro_original"] = str(erro_original).strip()

    for field in ["Placa", "Renavam", "CNPJ"]:
        value = row.get(field)
        if pd.notna(value):
            text_value = str(value).strip()
            if text_value:
                occurrence[field.lower()] = text_value

    return occurrence
