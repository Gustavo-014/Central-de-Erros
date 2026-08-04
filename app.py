from typing import Any

import pyperclip
import streamlit as st

from core.excel_reader import read_excel
from core.message_builder import build_messages
from core.processor import process_dataframe
from core.validator import validate_columns

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
        is_valid, missing_columns = validate_columns(dataframe)

        if not is_valid:
            st.error(
                "Planilha inválida. As colunas obrigatórias abaixo estão ausentes: "
                + ", ".join(missing_columns)
            )
        else:
            st.write(f"Quantidade de linhas: {len(dataframe)}")
            st.write(f"Quantidade de colunas: {len(dataframe.columns)}")
            st.dataframe(dataframe.head(10))

            dados, erros_sem_template = process_dataframe(dataframe)

            with st.expander("Resumo do processamento"):
                for cliente, erros in dados.items():
                    st.write(f"Nome do cliente: {cliente}")
                    st.write(f"Quantidade de tipos de erro: {len(erros)}")
                    total_placas = sum(len(placas) for placas in erros.values())
                    st.write(f"Quantidade total de placas: {total_placas}")

                    for erro, placas in erros.items():
                        st.write(f"Erro: {erro}")
                        st.write(f"Placas: {', '.join(placas)}")

                    st.write("")

            mensagens = build_messages(dados)

            st.subheader("Mensagens Geradas")
            st.write(f"Clientes: {len(mensagens)}")

            termo_pesquisa = st.text_input("Pesquisar cliente")
            clientes_filtrados = [
                cliente for cliente in mensagens if termo_pesquisa.lower() in cliente.lower()
            ]

            for cliente, mensagem in mensagens.items():
                if cliente not in clientes_filtrados:
                    continue

                with st.expander(cliente):
                    st.text_area("Mensagem", mensagem, height=300)
                    if st.button(f"📋 Copiar - {cliente}"):
                        pyperclip.copy(mensagem)
                        st.success("Mensagem copiada com sucesso.")

            st.subheader("⚠️ Erros sem template")
            if erros_sem_template:
                for erro in erros_sem_template:
                    st.write(f"• {erro}")
            else:
                st.write("Nenhum erro pendente de cadastro.")
