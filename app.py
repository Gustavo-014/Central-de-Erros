from typing import Any

import streamlit as st

from core.excel_reader import read_excel

st.set_page_config(page_title="Central de Erros", page_icon="🚗")

st.title("🚗 Central de Erros")
st.write("Sistema para automatização da comunicação de erros aos clientes.")

uploaded_file = st.file_uploader("Enviar planilha", type=["xlsx", "xlsm"])

if uploaded_file is None:
    st.write("Aguardando envio da planilha.")
else:
    st.write(f"Nome do arquivo: {uploaded_file.name}")
    st.write(f"Tamanho do arquivo: {uploaded_file.size} bytes")

    try:
        dataframe: Any = read_excel(uploaded_file)
    except ValueError as exc:
        st.error(str(exc))
    else:
        st.write(f"Quantidade de linhas: {len(dataframe)}")
        st.write(f"Quantidade de colunas: {len(dataframe.columns)}")
        st.dataframe(dataframe.head(10))
