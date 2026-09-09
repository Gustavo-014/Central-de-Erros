import re
from io import BytesIO
from typing import Dict

import pandas as pd


def count_errors_by_account(dataframe: pd.DataFrame) -> Dict[str, int]:
    """Conta quantos registros com erro cada 'Nome da Conta' possui no DataFrame original.

    Apenas linhas que possuem 'Mensagem de Erro' preenchida são contabilizadas.
    Retorna um dicionário {nome_da_conta: quantidade_de_registros}.
    """
    df = dataframe.copy()

    # Filtrar apenas linhas com Mensagem de Erro preenchida
    if "Mensagem de Erro" in df.columns:
        df = df[df["Mensagem de Erro"].notna() & (df["Mensagem de Erro"].astype(str).str.strip() != "")]

    # Filtrar apenas linhas com Nome da Conta preenchido
    if "Nome da Conta" in df.columns:
        df = df[df["Nome da Conta"].notna() & (df["Nome da Conta"].astype(str).str.strip() != "")]
    else:
        return {}

    return df["Nome da Conta"].astype(str).str.strip().value_counts().to_dict()


def export_account_errors_to_excel(dataframe: pd.DataFrame, account_name: str) -> bytes:
    """Exporta todos os registros de erro de uma conta específica para um arquivo Excel em memória.

    Filtra o DataFrame original pelo 'Nome da Conta' e inclui todas as colunas
    da planilha importada. Os valores são preservados exatamente como estão no
    DataFrame original, sem formatação, normalização ou transformação.

    Retorna os bytes do arquivo .xlsx pronto para download.
    """
    # Filtrar registros da conta, preservando dados originais
    mask = (
        dataframe["Nome da Conta"].notna()
        & (dataframe["Nome da Conta"].astype(str).str.strip() == account_name)
        & dataframe["Mensagem de Erro"].notna()
        & (dataframe["Mensagem de Erro"].astype(str).str.strip() != "")
    )
    df_account = dataframe.loc[mask].copy()

    # Gerar arquivo Excel em memória
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_account.to_excel(writer, index=False, sheet_name="Erros")
    buffer.seek(0)

    return buffer.getvalue()


def sanitize_filename(name: str) -> str:
    """Remove caracteres inválidos para nomes de arquivo no Windows.

    Preserva o nome original o máximo possível, removendo apenas os caracteres
    que impedem o salvamento do arquivo: \\ / : * ? \" < > |
    """
    return re.sub(r'[\\/:*?"<>|]', "", name).strip()
