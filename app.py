import importlib
import json
import urllib.parse
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import core.db
importlib.reload(core.db)

from core.db import (
    check_errors_sent_recently,
    delete_client_contact,
    get_all_contacts,
    get_client_contact,
    register_client_all_errors_sent,
    save_client_contact,
)
from core.daily_db import get_snapshot_by_date
from core.daily_service import compute_file_hash, extract_date_from_filename, record_daily_snapshot
from core.daily_ui import render_acompanhamento_tab
from core.excel_reader import read_excel
from core.excel_exporter import count_errors_by_account, export_account_errors_to_excel, sanitize_filename
from core.message_builder import build_messages
from core.processor import process_dataframe
from core.validator import validate_columns
from core.whatsapp_desktop import open_group_in_whatsapp_desktop

# Cooldown fixo de 1 dia (24h)
COOLDOWN_DAYS = 1

# Configuração da Página
st.set_page_config(
    page_title="Central de Erros - Brobot",
    layout="wide"
)

# Inicializar Estado de Mensagens Enviadas e Resolvidas no Session State
if "enviados" not in st.session_state:
    st.session_state.enviados = {}
if "resolvidos" not in st.session_state:
    st.session_state.resolvidos = {}

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
        margin-bottom: 1.5rem;
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

    /* Alerta de Cooldown / Duplicidade */
    .cooldown-alert {
        background: rgba(234, 179, 8, 0.12);
        border: 1px solid rgba(234, 179, 8, 0.4);
        color: #fde047;
        padding: 8px 12px;
        border-radius: 8px;
        font-size: 0.85rem;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        gap: 6px;
    }

    /* Alerta de Resolvido Anteriormente */
    .resolved-alert {
        background: rgba(16, 185, 129, 0.12);
        border: 1px solid rgba(16, 185, 129, 0.4);
        color: #6ee7b7;
        padding: 8px 12px;
        border-radius: 8px;
        font-size: 0.85rem;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        gap: 6px;
    }

    /* Tag de Contato */
    .contact-badge {
        font-size: 0.85rem;
        padding: 6px 12px;
        border-radius: 8px;
        background: rgba(99, 102, 241, 0.2);
        color: #c7d2fe;
        border: 1px solid rgba(139, 92, 246, 0.4);
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        justify-content: space-between;
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
st.markdown('<div class="sub-title">Automação de comunicação de erros de usuário e integração WhatsApp.</div>', unsafe_allow_html=True)

# Barra Lateral: Gestão de Contatos WhatsApp
with st.sidebar:
    st.markdown("### 📱 Grupos e Contatos WhatsApp")
    st.caption("Cadastre o **Nome do Grupo no WhatsApp** ou o telefone para cada cliente.")
    
    with st.expander("➕ Cadastrar / Editar Contato", expanded=False):
        novo_cliente = st.text_input("Nome do Cliente (Nome da Conta)", key="side_cli_nome")
        tipo_contato = st.selectbox(
            "Tipo de Destino",
            options=["Nome do Grupo no WhatsApp", "Telefone (Individual)", "Link de Convite"],
            index=0,
            key="side_tipo_contato"
        )
        
        tipo_map = {
            "Nome do Grupo no WhatsApp": "group_name",
            "Telefone (Individual)": "phone",
            "Link de Convite": "group_link",
        }
        
        placeholder_text = (
            "Ex: Frota ABC - Suporte" if tipo_contato == "Nome do Grupo no WhatsApp"
            else "Ex: 11999998888" if tipo_contato == "Telefone (Individual)"
            else "Ex: https://chat.whatsapp.com/..."
        )
        novo_contato = st.text_input("Identificador / Valor", key="side_cli_contato", placeholder=placeholder_text)
        
        if st.button("💾 Salvar Destino", use_container_width=True):
            if novo_cliente and novo_contato:
                sucesso, msg = save_client_contact(novo_cliente, novo_contato, tipo_map[tipo_contato])
                if sucesso:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
            else:
                st.warning("Preencha todos os campos.")

    # Lista de contatos existentes
    contatos_cadastrados = get_all_contacts()
    if contatos_cadastrados:
        with st.expander(f"📋 Destinos Cadastrados ({len(contatos_cadastrados)})", expanded=False):
            for cli, info in list(contatos_cadastrados.items()):
                tipo = info.get("contact_type", "group_name")
                c_tipo_icon = "👥 Grupo" if tipo == "group_name" else "📞 Tel" if tipo == "phone" else "🔗 Link"
                st.markdown(f"**{cli}**  \n`{c_tipo_icon}: {info['contact_value']}`")
                if st.button(f"🗑️ Remover {cli}", key=f"del_{cli}"):
                    delete_client_contact(cli)
                    st.rerun()
                st.write("---")
    else:
        st.info("Nenhum grupo ou contato cadastrado ainda.")

    st.divider()
    st.caption("🛡️ **Cooldown Automático:** Bloqueio de reenvios do mesmo erro configurado para **1 dia**.")

# Funções de Renderização de Botões (Copy e WhatsApp)
def render_action_buttons(text_to_copy: str, client_id: str, contact_info: Optional[Dict[str, str]]):
    """Renderiza os botões de ação: Copiar Mensagem e Abrir WhatsApp com texto copiado."""
    escaped_text = json.dumps(text_to_copy)
    
    wa_button_html = ""
    if contact_info:
        c_type = contact_info.get("contact_type", "group_name")
        c_val = contact_info.get("contact_value", "")
        escaped_group = json.dumps(c_val)
        
        if c_type == "phone":
            encoded_msg = urllib.parse.quote(text_to_copy)
            wa_url = f"https://wa.me/{c_val}?text={encoded_msg}"
            wa_button_html = f"""
            <a href="{wa_url}" target="_blank" class="wa-btn" style="text-decoration:none;">
                🟢 Abrir no WhatsApp
            </a>
            """
        elif c_type == "group_link":
            wa_button_html = f"""
            <a href="{c_val}" target="_blank" class="wa-btn" style="text-decoration:none;" onclick='
                navigator.clipboard.writeText({escaped_text});
            '>
                👥 Abrir Grupo (Texto Copiado)
            </a>
            """
        else:
            # group_name: o envio e busca são feitos pelo botão nativo de WhatsApp Desktop
            wa_button_html = ""

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
            display: flex;
            gap: 10px;
        }}
        .copy-btn {{
            flex: 1;
            padding: 9px 14px;
            background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
            color: #ffffff;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 13.5px;
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
        .wa-btn {{
            flex: 1.2;
            padding: 9px 14px;
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            color: #ffffff;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 13.5px;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
            transition: all 0.15s ease-in-out;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }}
        .wa-btn:hover {{
            background: linear-gradient(135deg, #059669 0%, #047857 100%);
            box-shadow: 0 6px 16px rgba(16, 185, 129, 0.45);
            transform: translateY(-1px);
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
        {wa_button_html}
    </body>
    </html>
    """
    components.html(html_code, height=45)

def render_operacional_tab():
    # 1. Campo Obrigatório: Data da análise / Data do Daily
    col_up_date, col_up_file = st.columns([1.3, 2.7])
    with col_up_date:
        data_analise = st.date_input(
            "📅 **Data da análise / Data do Daily:**",
            value=datetime.now().date(),
            format="DD/MM/YYYY",
            help="Selecione a data oficial que este arquivo representa para o histórico e comparações da Daily.",
            key="data_analise_input",
        )
    with col_up_file:
        uploaded_file = st.file_uploader(
            "Selecione ou arraste a planilha (.xlsx, .xlsm)",
            type=["xlsx", "xlsm"],
            key="operacional_file_uploader",
        )

    if uploaded_file is None:
        st.info("💡 **Aguardando envio da planilha.** Defina a data da análise e selecione um arquivo para começar.")
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
                dados, erros_sem_template = process_dataframe(dataframe)
                mensagens = build_messages(dados)
                contagem_registros = count_errors_by_account(dataframe)

                # Persistência do snapshot diário com verificação e confirmação de duplicidade
                target_date_str = data_analise.strftime("%Y-%m-%d")
                target_date_fmt = data_analise.strftime("%d/%m/%Y")
                file_bytes = uploaded_file.getvalue()
                file_hash = compute_file_hash(file_bytes)

                existing_snap = get_snapshot_by_date(target_date_str)
                replace_key = f"confirmed_replace_{target_date_str}_{file_hash}"
                cancel_key = f"cancelled_replace_{target_date_str}_{file_hash}"

                if existing_snap and existing_snap["file_hash"] != file_hash:
                    # Já existe snapshot para a data com conteúdo diferente
                    if st.session_state.get(replace_key, False):
                        # Usuário confirmou a substituição
                        try:
                            ok_snap, msg_snap = record_daily_snapshot(
                                dados=dados,
                                dataframe=dataframe,
                                filename=uploaded_file.name,
                                file_bytes=file_bytes,
                                target_date=target_date_str,
                                force_replace=True,
                            )
                            st.session_state["daily_snapshot_status"] = (ok_snap, f"Dados substituídos: {msg_snap}", target_date_str)
                        except Exception as snap_exc:
                            st.session_state["daily_snapshot_status"] = (False, f"Falha ao substituir snapshot diário: {snap_exc}", target_date_str)
                    elif st.session_state.get(cancel_key, False):
                        st.info(f"ℹ️ Substituição cancelada para **{target_date_fmt}**. Os dados históricos anteriores foram preservados.")
                    else:
                        # Exibir alerta claro com botões de confirmação
                        orig_file = existing_snap.get("file_name", "planilha anterior")
                        orig_tot = existing_snap.get("total_erros", 0)
                        st.warning(
                            f"⚠️ **Já existe um histórico salvo para {target_date_fmt}.**\n\n"
                            f"• Histórico atual: arquivo `{orig_file}` ({orig_tot} erros)\n\n"
                            f"Se você continuar, os dados desse dia serão **substituídos** pelo arquivo atual (`{uploaded_file.name}`)."
                        )
                        col_c, col_s = st.columns([1, 1.8])
                        with col_c:
                            if st.button("❌ Cancelar", key=f"btn_cancel_{target_date_str}_{file_hash}"):
                                st.session_state[cancel_key] = True
                                st.session_state[replace_key] = False
                                st.rerun()
                        with col_s:
                            if st.button("🔄 Substituir dados", type="primary", key=f"btn_subst_{target_date_str}_{file_hash}"):
                                try:
                                    ok_snap, msg_snap = record_daily_snapshot(
                                        dados=dados,
                                        dataframe=dataframe,
                                        filename=uploaded_file.name,
                                        file_bytes=file_bytes,
                                        target_date=target_date_str,
                                        force_replace=True,
                                    )
                                    st.session_state[replace_key] = True
                                    st.session_state[cancel_key] = False
                                    st.session_state["daily_snapshot_status"] = (ok_snap, f"Dados substituídos: {msg_snap}", target_date_str)
                                except Exception as snap_exc:
                                    st.session_state["daily_snapshot_status"] = (False, f"Falha ao substituir snapshot diário: {snap_exc}", target_date_str)
                                st.rerun()
                else:
                    # Não existe ou mesmo arquivo: gravar normalmente
                    process_key = f"{file_hash}_{target_date_str}"
                    if st.session_state.get("last_processed_key") != process_key:
                        try:
                            ok_snap, msg_snap = record_daily_snapshot(
                                dados=dados,
                                dataframe=dataframe,
                                filename=uploaded_file.name,
                                file_bytes=file_bytes,
                                target_date=target_date_str,
                                force_replace=False,
                            )
                            st.session_state["last_processed_key"] = process_key
                            st.session_state["daily_snapshot_status"] = (ok_snap, msg_snap, target_date_str)
                        except Exception as snap_exc:
                            st.session_state["daily_snapshot_status"] = (False, f"Falha ao salvar snapshot diário: {snap_exc}", target_date_str)

                st.divider()

                # Pré-calcular histórico de duplicidades/cooldown por cliente
                duplicidades_por_cliente = {}
                for cliente in mensagens:
                    erros_cli = list(dados.get(cliente, {}).keys())
                    hist = check_errors_sent_recently(cliente, erros_cli, days=COOLDOWN_DAYS)
                    duplicidades_por_cliente[cliente] = {err: dt for err, dt in hist.items() if dt is not None}

                # Garantir chaves no session_state para cada cliente
                for cliente in mensagens:
                    if cliente not in st.session_state.enviados:
                        st.session_state.enviados[cliente] = False
                    if cliente not in st.session_state.resolvidos:
                        st.session_state.resolvidos[cliente] = False

                total_clientes = len(mensagens)
                total_enviados = sum(1 for v in st.session_state.enviados.values() if v)
                total_resolvidos = sum(1 for v in st.session_state.resolvidos.values() if v)
                # Concluídos considera enviados, resolvidos e já notificados recentemente (cooldown)
                total_concluidos = sum(
                    1 for c in mensagens 
                    if st.session_state.enviados.get(c, False) 
                    or st.session_state.resolvidos.get(c, False) 
                    or len(duplicidades_por_cliente.get(c, {})) > 0
                )
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
                            <div class="metric-value">{total_concluidos} / {total_clientes}</div>
                            <div class="metric-label">Concluídos</div>
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
                    progresso = total_concluidos / total_clientes
                    st.progress(progresso)

                if "daily_snapshot_status" in st.session_state:
                    status_tuple = st.session_state["daily_snapshot_status"]
                    ok_s = status_tuple[0]
                    msg_s = status_tuple[1]
                    d_s = status_tuple[2] if len(status_tuple) > 2 else ""
                    try:
                        d_fmt = datetime.strptime(d_s, "%Y-%m-%d").strftime("%d/%m/%Y")
                        dt_label = f" ({d_fmt})"
                    except Exception:
                        dt_label = ""
                    if ok_s:
                        st.caption(f"💾 **Histórico Daily{dt_label}:** {msg_s} *(Acesse a aba 📊 Acompanhamento para filtrar e analisar)*")
                    else:
                        st.warning(f"⚠️ **Histórico Daily{dt_label}:** {msg_s}")

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
                        erros_do_cliente = list(dados.get(cliente, {}).keys())
                        qtd_erros = len(erros_do_cliente)
                        is_enviado = st.session_state.enviados.get(cliente, False)
                        is_resolvido = st.session_state.resolvidos.get(cliente, False)

                        # Recuperar histórico de cooldown pré-calculado
                        historico_cliente = duplicidades_por_cliente.get(cliente, {})
                        erros_resolvidos_ant = {err: info["sent_at"] for err, info in historico_cliente.items() if info.get("channel") == "resolvido"}
                        erros_notificados_ant = {err: info["sent_at"] for err, info in historico_cliente.items() if info.get("channel") != "resolvido"}

                        tem_resolvido = len(erros_resolvidos_ant) > 0
                        tem_notificado = len(erros_notificados_ant) > 0

                        # Buscar contato / nome de grupo cadastrado
                        contact_info = get_client_contact(cliente)

                        # Título dinâmico do card com status
                        if is_enviado:
                            status_prefix = "✅ "
                            status_suffix = " — [ENVIADO]"
                        elif is_resolvido:
                            status_prefix = "🔧 "
                            status_suffix = " — [RESOLVIDO]"
                        elif tem_resolvido:
                            status_prefix = "🔧 "
                            status_suffix = " — [JÁ RESOLVIDO HOJE/ONTEM]"
                        elif tem_notificado:
                            status_prefix = "⏳ "
                            status_suffix = " — [JÁ NOTIFICADO HOJE/ONTEM]"
                        else:
                            status_prefix = "🏢 "
                            status_suffix = ""

                        expander_label = f"{status_prefix}**{cliente}** ({qtd_erros} tipo{'s' if qtd_erros > 1 else ''} de erro){status_suffix}"

                        with st.expander(expander_label):
                            # Alerta se houver erro já resolvido recentemente (1 dia)
                            if tem_resolvido:
                                st.markdown(
                                    """
                                    <div class="resolved-alert">
                                        <span>🔧 <b>Atenção (Resolvido recentemente):</b> Este erro já foi marcado como resolvido para este cliente:</span>
                                    </div>
                                    """,
                                    unsafe_allow_html=True
                                )
                                for err_nome, data_envio in erros_resolvidos_ant.items():
                                    try:
                                        dt_fmt = datetime.strptime(data_envio, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y às %H:%M")
                                    except Exception:
                                        dt_fmt = data_envio
                                    st.caption(f"• **{err_nome}** (resolvido em {dt_fmt})")

                            # Alerta se houver erro já enviado recentemente (1 dia)
                            if tem_notificado:
                                st.markdown(
                                    """
                                    <div class="cooldown-alert">
                                        <span>⏳ <b>Atenção (Cooldown 1 dia):</b> Este cliente já recebeu notificação recente para:</span>
                                    </div>
                                    """,
                                    unsafe_allow_html=True
                                )
                                for err_nome, data_envio in erros_notificados_ant.items():
                                    try:
                                        dt_fmt = datetime.strptime(data_envio, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y às %H:%M")
                                    except Exception:
                                        dt_fmt = data_envio
                                    st.caption(f"• **{err_nome}** (enviado em {dt_fmt})")

                            # Exibição do grupo cadastrado ou opção de cadastro rápido
                            if contact_info:
                                c_type = contact_info.get("contact_type", "group_name")
                                c_tipo_label = (
                                    "Grupo no WhatsApp" if c_type == "group_name"
                                    else "Telefone" if c_type == "phone"
                                    else "Link do Grupo"
                                )
                                st.markdown(
                                    f"""
                                    <div class="contact-badge">
                                        <span>👥 <b>{c_tipo_label}:</b> <code>{contact_info['contact_value']}</code></span>
                                    </div>
                                    """,
                                    unsafe_allow_html=True
                                )
                            else:
                                st.caption("ℹ️ *Grupo ou contato do WhatsApp ainda não cadastrado para este cliente.*")
                                with st.expander("➕ Vincular Nome do Grupo no WhatsApp", expanded=False):
                                    quick_nome_grupo = st.text_input(
                                        "Nome do Grupo no WhatsApp",
                                        key=f"quick_g_{cliente}_{index}",
                                        placeholder="Ex: Suporte - Frota ABC"
                                    )
                                    if st.button("Salvar Grupo", key=f"btn_save_{cliente}_{index}"):
                                        if quick_nome_grupo:
                                            ok, msg = save_client_contact(cliente, quick_nome_grupo, "group_name")
                                            if ok:
                                                st.success(msg)
                                                st.rerun()
                                            else:
                                                st.error(msg)

                            # Checkboxes de Controle lado a lado
                            col_env, col_res = st.columns(2)

                            with col_env:
                                enviado_check = st.checkbox(
                                    "✅ Enviado ao cliente",
                                    value=is_enviado,
                                    key=f"chk_env_{cliente}_{index}"
                                )
                            with col_res:
                                resolvido_check = st.checkbox(
                                    "🔧 Resolvido",
                                    value=is_resolvido,
                                    key=f"chk_res_{cliente}_{index}"
                                )

                            # Exclusividade mútua + atualização de estado e registro no SQLite
                            changed = False
                            if enviado_check != is_enviado:
                                st.session_state.enviados[cliente] = enviado_check
                                if enviado_check:
                                    st.session_state.resolvidos[cliente] = False
                                    # Registrar no histórico SQLite como enviado
                                    register_client_all_errors_sent(cliente, erros_do_cliente, channel="whatsapp")
                                changed = True
                            elif resolvido_check != is_resolvido:
                                st.session_state.resolvidos[cliente] = resolvido_check
                                if resolvido_check:
                                    st.session_state.enviados[cliente] = False
                                    # Registrar no histórico SQLite como resolvido
                                    register_client_all_errors_sent(cliente, erros_do_cliente, channel="resolvido")
                                changed = True
                            if changed:
                                st.rerun()

                            # Área de texto com a mensagem
                            st.text_area(
                                label="Mensagem Pronta",
                                value=mensagem,
                                height=250,
                                key=f"msg_{cliente}_{index}",
                                label_visibility="collapsed"
                            )

                            # Botão de Exportação Excel (contas com mais de 10 registros)
                            qtd_registros_conta = contagem_registros.get(cliente, 0)
                            if qtd_registros_conta > 10:
                                excel_bytes = export_account_errors_to_excel(dataframe, cliente)
                                nome_arquivo = f"{sanitize_filename(cliente)} - Erros de usuários.xlsx"
                                st.download_button(
                                    label=f"📥 Exportar Excel ({qtd_registros_conta} registros)",
                                    data=excel_bytes,
                                    file_name=nome_arquivo,
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    key=f"dl_excel_{cliente}_{index}",
                                )

                            # Botões de Ação lado a lado (50% / 50%)
                            if contact_info and contact_info.get("contact_type") == "group_name":
                                nome_grupo_alvo = contact_info.get("contact_value", "")
                                col_btn_desk, col_btn_copy = st.columns([1, 1])

                                with col_btn_desk:
                                    if st.button(
                                        f"🚀 Abrir no WhatsApp Desktop",
                                        key=f"btn_wa_desk_{cliente}_{index}",
                                        type="primary",
                                        use_container_width=True,
                                        help=f"Abre o WhatsApp Desktop, pesquisa por '{nome_grupo_alvo}', entra na conversa e já cola o texto na caixa de envio.",
                                    ):
                                        with st.spinner(f"Abrindo WhatsApp Desktop e localizando '{nome_grupo_alvo}'..."):
                                            ok_desk, msg_desk = open_group_in_whatsapp_desktop(nome_grupo_alvo, mensagem)
                                            if ok_desk:
                                                st.toast(f"✅ {msg_desk}", icon="🚀")
                                            else:
                                                st.error(f"⚠️ {msg_desk}")

                                with col_btn_copy:
                                    render_action_buttons(mensagem, client_id=f"cli_{index}", contact_info=contact_info)
                            else:
                                render_action_buttons(mensagem, client_id=f"cli_{index}", contact_info=contact_info)

                # Avisos de Erros sem Template (Discreto no final)
                if erros_sem_template:
                    st.write("")
                    with st.expander("⚠️ **Aviso: Erros pendentes de cadastro de template**"):
                        st.write("Os seguintes erros foram encontrados na planilha mas não possuem template cadastrado no sistema:")
                        for erro in erros_sem_template:
                            st.write(f"• `{erro}`")


# Navegação Principal em Abas
tab_operacional, tab_acompanhamento = st.tabs(["⚡ Operacional (Envio)", "📊 Acompanhamento"])

with tab_operacional:
    render_operacional_tab()

with tab_acompanhamento:
    render_acompanhamento_tab()
