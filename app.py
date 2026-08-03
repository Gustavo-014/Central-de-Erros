import streamlit as st

st.set_page_config(page_title="Central de Erros", page_icon="🚗")

st.title("🚗 Central de Erros")
st.write("Sistema para automatização da comunicação de erros aos clientes.")

uploaded_file = st.file_uploader("Enviar planilha", type=["xlsx", "xlsm"])

if uploaded_file is None:
    st.write("Aguardando envio da planilha.")
else:
    st.write(f"Nome do arquivo: {uploaded_file.name}")
    st.write(f"Tamanho do arquivo: {uploaded_file.size} bytes")
    st.write("Nenhum processamento ainda.")
