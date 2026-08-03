from io import BytesIO
from typing import Any

import pandas as pd


def read_excel(uploaded_file: Any) -> pd.DataFrame:
    """Lê uma planilha Excel enviada pelo Streamlit e retorna um DataFrame."""
    if uploaded_file is None:
        raise ValueError("Nenhum arquivo foi enviado.")

    try:
        file_bytes = uploaded_file.getvalue()
        return pd.read_excel(BytesIO(file_bytes), engine="openpyxl")
    except Exception as exc:
        raise ValueError(f"Não foi possível ler a planilha: {exc}") from exc
