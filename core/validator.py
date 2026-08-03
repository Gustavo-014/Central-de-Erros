from typing import List, Tuple

import pandas as pd


def validate_columns(dataframe: pd.DataFrame) -> Tuple[bool, List[str]]:
    """Valida se o DataFrame possui as colunas obrigatórias da planilha."""
    required_columns = ["Nome da Conta", "Placa", "Mensagem de Erro"]
    missing_columns = [column for column in required_columns if column not in dataframe.columns]

    if missing_columns:
        return False, missing_columns

    return True, []
