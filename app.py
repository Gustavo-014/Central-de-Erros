from typing import Any

import pandas as pd
import pyperclip
import streamlit as st

from core.excel_reader import read_excel
from core.message_builder import build_messages
from core.processor import process_dataframe
from core.validator import validate_columns

# Configuração da Página
st.set_page_config(
    page_title="Central de Erros - Brobot",
    page_icon="🚗",
    layout="centered"
)

# Estilização CSS Personalizada (Tema Azul / Roxo Profundo)
st.markdown(
    """
    <style>
    /* Estilização Geral do Fundo e Tipografia */
    .main {
        background-color: #0b0f19;
    }
    
    /* Cabeçalho */
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #a5b4fc 0%, #6366f1 50%, #c084fc 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        color: #94a3b8;
        font-size: 1.0rem;
        margin-bottom: 1.8rem;
    }

    /* Container de Métricas Discretas */
    .metric-card {
        background: #151c2c;
        border: 1px solid #2a364f;
        border-radius: 10px;
        padding: 12px 18px;
        text-align: center;
    }
    .metric-value {
        font-size: 1.5rem;
        font-weight: 700;
        color: #818cf8;
    }
    .metric-label {
        font-size: 0.82rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    /* Caixa de Texto das Mensagens */
    div[data-baseweb="textarea"] textarea {
        background-color: #0f172a !important;
        color: #e2e8f0 !important;
        border: 1px solid #334155 !important;
        border-radius: 8px !important;
        font-family: 'Consolas', 'Courier New', monospace !important;
        font-size: 0.9rem !important;
    }

    /* Ajuste dos Expanders de Clientes */
    .stApp div[data-testid="stExpander"] {
        background-color: #151c2c;
        border: 1px solid #2a364f;
        border-radius: 10px;
        margin-bottom: 10px;
    }
    
    /* Botões Primários e Secundários */
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s ease-in-out;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Header da Aplicação
st.markdown('<div class="main-title">🚗 Central de Erros</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Envie a planilha para gerar automaticamente as mensagens de erro dos clientes.</div>', unsafe_allow_html=True)

# Upload de Arquivo
uploaded_file = st.file_uploader("Selecione ou arraste a planilha (.xlsx, .xlsm)", type=["xlsx", "xlsm"])

if uploaded_file is None:
    st.info("💡 **Aguardando envio da planilha.** Suba um arquivo para começar.")
else:
    try:
        dataframe: Any = read_excel(uploaded_file)
    except Exception as exc:
        st.error(f"Erro ao ler o arquivo Excel: {exc}")
    else:
        is_valid, missing_columns = validate_columns(dataframe)

        if not is_valid:
            st.error(
                "❌ **Planilha inválida.** As seguintes colunas obrigatórias estão ausentes:\n\n"
                + "\n".join([f"• `{col}`" for col in missing_columns])
            )
        else:
            # Processamento dos dados
            dados, erros_sem_template, _ = process_dataframe(dataframe)
            mensagens = build_messages(dados)

            st.divider()

            # Resumo em Métricas Elegantes
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(
                    f"""
                    <div class="metric-card">
                        <div class="metric-value">{len(mensagens)}</div>
                        <div class="metric-label">Clientes com Erros</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with col2:
                total_erros_unicos = sum(len(erros) for erros in dados.values())
                st.markdown(
                    f"""
                    <div class="metric-card">
                        <div class="metric-value">{total_erros_unicos}</div>
                        <div class="metric-label">Tipos de Erros Detectados</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            st.write("")

            # Pesquisa e Filtro por Cliente
            termo_pesquisa = st.text_input("🔍 Pesquisar Cliente", placeholder="Digite o nome do cliente...")
            
            clientes_filtrados = [
                cliente for cliente in mensagens 
                if not termo_pesquisa or termo_pesquisa.lower() in cliente.lower()
            ]

            st.write("")

            if not clientes_filtrados:
                st.warning("Nenhum cliente encontrado com esse nome.")
            else:
                for cliente in clientes_filtrados:
                    mensagem = mensagens[cliente]
                    qtd_erros = len(dados.get(cliente, {}))
                    
                    with st.expander(f"🏢 **{cliente}** ({qtd_erros} tipo{'s' if qtd_erros > 1 else ''} de erro)"):
                        st.text_area(
                            label="Mensagem Pronta",
                            value=mensagem,
                            height=250,
                            key=f"msg_{cliente}",
                            label_visibility="collapsed"
                        )
                        
                        col_btn, _ = st.columns([1, 2])
                        with col_btn:
                            if st.button(f"📋 Copiar Mensagem", key=f"btn_{cliente}", use_container_width=True):
                                pyperclip.copy(mensagem)
                                st.toast(f"Mensagem de {cliente} copiada!", icon="✅")

            # Avisos de Erros sem Template (Discreto no final)
            if erros_sem_template:
                st.write("")
                with st.expander("⚠️ **Aviso: Erros pendentes de cadastro de template**"):
                    st.write("Os seguintes erros foram encontrados na planilha mas não possuem template cadastrado no sistema:")
                    for erro in erros_sem_template:
                        st.write(f"• `{erro}`")
