from typing import Dict, List

import pandas as pd


def process_dataframe(dataframe: pd.DataFrame) -> Dict[str, Dict[str, List[str]]]:
    """Organiza os dados da planilha em estrutura agrupada por cliente e erro."""
    result: Dict[str, Dict[str, List[str]]] = {}

    for _, row in dataframe.iterrows():
        cliente = str(row.get("Nome da Conta", "")).strip()
        placa = str(row.get("Placa", "")).strip()
        mensagem = str(row.get("Mensagem de Erro", "")).strip()

        if not cliente or not placa or not mensagem:
            continue

        if cliente not in result:
            result[cliente] = {}

        if mensagem not in result[cliente]:
            result[cliente][mensagem] = []

        if placa not in result[cliente][mensagem]:
            result[cliente][mensagem].append(placa)

    for cliente in result:
        for erro in result[cliente]:
            result[cliente][erro] = sorted(result[cliente][erro])

    return {
        cliente: {erro: result[cliente][erro] for erro in sorted(result[cliente])}
        for cliente in sorted(result)
    }
