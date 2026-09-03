import re
from typing import Any, Dict, Optional

import pandas as pd


def _format_cnpj(value: object) -> Optional[str]:
    """Converte um valor bruto de CNPJ (número ou string) para o formato XX.XXX.XXX/XXXX-XX."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None

    # Remover parte decimal introduzida pelo Excel (ex: 12345678000195.0 → "12345678000195")
    raw = str(value).strip()
    raw = re.sub(r"\.0+$", "", raw)  # tira .0, .00, etc.

    # Manter somente dígitos
    digits = re.sub(r"\D", "", raw)

    if not digits:
        return None

    # Preencher com zeros à esquerda até 14 dígitos
    digits = digits.zfill(14)

    # Formatar: XX.XXX.XXX/XXXX-XX
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:14]}"


def _format_renavam(value: object) -> Optional[str]:
    """Converte um valor bruto de Renavam (número ou string) para 11 dígitos com zeros à esquerda."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None

    # Remover parte decimal introduzida pelo Excel (ex: 12345678901.0 → "12345678901")
    raw = str(value).strip()
    raw = re.sub(r"\.0+$", "", raw)  # tira .0, .00, etc.

    # Manter somente dígitos
    digits = re.sub(r"\D", "", raw)

    if not digits:
        return None

    # Preencher com zeros à esquerda até 11 dígitos
    return digits.zfill(11)


def extract_occurrence(row: Dict[str, Any]) -> Dict[str, Optional[str]]:
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

    placa = row.get("Placa")
    if pd.notna(placa):
        text_value = str(placa).strip()
        if text_value:
            occurrence["placa"] = text_value

    renavam_raw = row.get("Renavam")
    renavam_formatted = _format_renavam(renavam_raw)
    if renavam_formatted:
        occurrence["renavam"] = renavam_formatted

    cnpj_raw = row.get("CNPJ")
    cnpj_formatted = _format_cnpj(cnpj_raw)
    if cnpj_formatted:
        occurrence["cnpj"] = cnpj_formatted

    return occurrence
