import json
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from core.excel_reader import read_excel
from core.message_builder import build_messages
from core.processor import process_dataframe
from core.validator import validate_columns

# Configuração da Página
st.set_page_config(
    page_title="Central de Erros - Brobot",
    layout="centered"
)

# Inicializar Estado de Mensagens Enviadas no Session State
if "enviados" not in st.session_state:
    st.session_state.enviados = {}

# Estilização CSS Avançada (Fundo Violeta/Índigo com Gradiente Fluido & Glassmorphism)
st.markdown(
    """
    <style>
    /* Fundo Gradiente Fluido Noturno */
    .stApp {
        background: radial-gradient(circle at 50% -10%, #2e1065 0%, #0f172a 55%, #070a12 100%) !important;
        background-attachment: fixed !important;
    }
    
    /* Cabeçalho de Alto Impacto */
    .main-title {
        font-size: 2.5rem;
        font-weight: 800;
        background: linear-gradient(135deg, #c084fc 0%, #818cf8 50%, #38bdf8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
        letter-spacing: -0.5px;
    }
    .sub-title {
        color: #94a3b8;
        font-size: 1.05rem;
        margin-bottom: 2rem;
    }

    /* Cards de Métricas em Glassmorphism */
    .metric-card {
        background: rgba(21, 28, 44, 0.7);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(139, 92, 246, 0.25);
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        border-radius: 12px;
        padding: 14px 20px;
        text-align: center;
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .metric-card:hover {
        border-color: rgba(168, 85, 247, 0.5);
        transform: translateY(-2px);
    }
    .metric-value {
        font-size: 1.7rem;
        font-weight: 800;
        color: #c084fc;
    }
    .metric-label {
        font-size: 0.8rem;
        color: #cbd5e1;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        font-weight: 600;
    }

    /* Barra de Progresso Estilizada */
    .stProgress > div > div > div > div {
        background-image: linear-gradient(90deg, #818cf8, #c084fc) !important;
    }

    /* Caixa de Texto das Mensagens */
    div[data-baseweb="textarea"] textarea {
        background-color: rgba(15, 23, 42, 0.95) !important;
        color: #f1f5f9 !important;
        border: 1px solid rgba(139, 92, 246, 0.3) !important;
        border-radius: 10px !important;
        font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace !important;
        font-size: 0.92rem !important;
        line-height: 1.5 !important;
    }

    /* Estilização dos Expanders (Cards de Clientes) */
    .stApp div[data-testid="stExpander"] {
        background: rgba(17, 24, 39, 0.65) !important;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(124, 58, 237, 0.2) !important;
        border-radius: 12px !important;
        margin-bottom: 12px !important;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
    }
    .stApp div[data-testid="stExpander"]:hover {
        border-color: rgba(168, 85, 247, 0.4) !important;
    }

    /* Estilização para Clientes Marcados como Enviados */
    .client-enviado {
        opacity: 0.65;
    }
    
    /* Input de Pesquisa */
    div[data-baseweb="input"] {
        background-color: rgba(15, 23, 42, 0.8) !important;
        border-radius: 10px !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Header da Aplicação
st.markdown('<div class="main-title">Central de Erros</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Automação de comunicação de erros de usuário.</div>', unsafe_allow_html=True)

# Upload de Arquivo
uploaded_file = st.file_uploader("Selecione ou arraste a planilha (.xlsx, .xlsm)", type=["xlsx", "xlsm"])

def render_instant_copy_button(text_to_copy: str, client_id: str):
    """Gera um botão em HTML/JS instantâneo (0ms de latência) sem recarregar o Python."""
    escaped_text = json.dumps(text_to_copy)
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body {{
            margin: 0;
            padding: 0;
            background: transparent;
            font-family: system-ui, -apple-system, sans-serif;
        }}
        .copy-btn {{
            width: 100%;
            padding: 9px 16px;
            background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
            color: #ffffff;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
            transition: all 0.15s ease-in-out;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }}
        .copy-btn:hover {{
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
            box-shadow: 0 6px 16px rgba(99, 102, 241, 0.45);
            transform: translateY(-1px);
        }}
        .copy-btn:active {{
            transform: translateY(0px);
        }}
        .copy-btn.copied {{
            background: #10b981 !important;
            box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3) !important;
        }}
    </style>
    </head>
    <body>
        <button id="btn_{client_id}" class="copy-btn" onclick='
            navigator.clipboard.writeText({escaped_text}).then(function() {{
                var btn = document.getElementById("btn_{client_id}");
                btn.innerText = "✅ Copiado!";
                btn.classList.add("copied");
                setTimeout(function() {{
                    btn.innerText = "📋 Copiar Mensagem";
                    btn.classList.remove("copied");
                }}, 1500);
            }}).catch(function(err) {{
                console.error("Erro ao copiar", err);
            }});
        '>📋 Copiar Mensagem</button>
    </body>
    </html>
    """
    components.html(html_code, height=45)

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

            # Garantir chaves no session_state para cada cliente
            for cliente in mensagens:
                if cliente not in st.session_state.enviados:
                    st.session_state.enviados[cliente] = False

            total_clientes = len(mensagens)
            total_enviados = sum(1 for v in st.session_state.enviados.values() if v)
            total_erros_unicos = sum(len(erros) for erros in dados.values())

            # Resumo em Métricas Elegantes com Progresso
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(
                    f"""
                    <div class="metric-card">
                        <div class="metric-value">{total_clientes}</div>
                        <div class="metric-label">Total Clientes</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with col2:
                st.markdown(
                    f"""
                    <div class="metric-card">
                        <div class="metric-value">{total_enviados} / {total_clientes}</div>
                        <div class="metric-label">Mensagens Enviadas</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with col3:
                st.markdown(
                    f"""
                    <div class="metric-card">
                        <div class="metric-value">{total_erros_unicos}</div>
                        <div class="metric-label">Tipos de Erros</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # Barra de progresso visual
            if total_clientes > 0:
                progresso = total_enviados / total_clientes
                st.progress(progresso)

            st.write("")

            # Pesquisa e Filtro por Cliente
            termo_pesquisa = st.text_input("🔍 Pesquisar Cliente", placeholder="Digite o nome do cliente...")
            
            clientes_filtrados = [
                cliente for cliente in mensagens 
                if not termo_pesquisa or termo_pesquisa.lower() in cliente.lower()
            ]

            st.write("")

            if not clientes_filtrados:
                st.warning("Nenhum cliente encontrado com esse termo de busca.")
            else:
                for index, cliente in enumerate(clientes_filtrados):
                    mensagem = mensagens[cliente]
                    qtd_erros = len(dados.get(cliente, {}))
                    is_enviado = st.session_state.enviados.get(cliente, False)

                    # Título dinâmico do card com status de envio
                    status_prefix = "✅ " if is_enviado else "🏢 "
                    status_suffix = " — [ENVIADO]" if is_enviado else ""
                    expander_label = f"{status_prefix}**{cliente}** ({qtd_erros} tipo{'s' if qtd_erros > 1 else ''} de erro){status_suffix}"

                    with st.expander(expander_label):
                        # Checkbox de Controle de Envio
                        enviado_check = st.checkbox(
                            "Marcar mensagem como enviada ao cliente",
                            value=is_enviado,
                            key=f"chk_{cliente}_{index}"
                        )
                        if enviado_check != is_enviado:
                            st.session_state.enviados[cliente] = enviado_check
                            st.rerun()

                        # Área de texto com a mensagem
                        st.text_area(
                            label="Mensagem Pronta",
                            value=mensagem,
                            height=250,
                            key=f"msg_{cliente}_{index}",
                            label_visibility="collapsed"
                        )
                        
                        # Botão de cópia INSTANTÂNEA via JS (sem reload de tela)
                        render_instant_copy_button(mensagem, client_id=f"cli_{index}")

            # Avisos de Erros sem Template (Discreto no final)
            if erros_sem_template:
                st.write("")
                with st.expander("⚠️ **Aviso: Erros pendentes de cadastro de template**"):
                    st.write("Os seguintes erros foram encontrados na planilha mas não possuem template cadastrado no sistema:")
                    for erro in erros_sem_template:
                        st.write(f"• `{erro}`")
