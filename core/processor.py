from typing import Dict, List, Tuple

import pandas as pd

from core.error_normalizer import normalize_error
from core.template_loader import load_templates


def process_dataframe(dataframe: pd.DataFrame) -> Tuple[Dict[str, Dict[str, List[str]]], List[str]]:
    """Organiza os dados da planilha em estrutura agrupada por cliente e erro."""
    result: Dict[str, Dict[str, List[str]]] = {}
    pending_errors: List[str] = []
    templates = load_templates()

    for _, row in dataframe.iterrows():
        cliente = str(row.get("Nome da Conta", "")).strip()
        placa = str(row.get("Placa", "")).strip()
        mensagem = str(row.get("Mensagem de Erro", "")).strip()

        erro_normalizado = normalize_error(mensagem)
        if erro_normalizado is None:
            continue

        if not cliente or not placa:
            continue

        if cliente not in result:
            result[cliente] = {}

        if erro_normalizado not in result[cliente]:
            result[cliente][erro_normalizado] = []

        if placa not in result[cliente][erro_normalizado]:
            result[cliente][erro_normalizado].append(placa)

        if erro_normalizado not in templates:
            if erro_normalizado not in pending_errors:
                pending_errors.append(erro_normalizado)

    for cliente in result:
        for erro in result[cliente]:
            result[cliente][erro] = sorted(result[cliente][erro])

    return (
        {
            cliente: {erro: result[cliente][erro] for erro in sorted(result[cliente])}
            for cliente in sorted(result)
        },
        pending_errors,
    )
