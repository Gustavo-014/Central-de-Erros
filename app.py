import json
import os
import urllib.parse
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import pyperclip
import streamlit as st

from core.db import (
    delete_client_contact,
    get_all_contacts,
    get_all_recent_cooldowns,
    get_client_contact,
    register_client_all_errors_sent,
    save_client_contact,
)
from core.daily_db import get_snapshot_by_date
from core.daily_service import compute_file_hash, extract_date_from_filename, record_daily_snapshot
from core.daily_ui import render_acompanhamento_tab
from core.client_service import record_client_history
from core.client_ui import render_cliente_tab
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
    page_title="Central de Erros | Brobot",
    page_icon=":material/analytics:",
    layout="wide"
)

# Inicializar Estado de Mensagens Enviadas e Resolvidas no Session State
if "enviados" not in st.session_state:
    st.session_state.enviados = {}
if "resolvidos" not in st.session_state:
    st.session_state.resolvidos = {}

# Carregamento do Design System CSS Externo
def load_css(css_rel_path: str = "static/style.css") -> None:
    """Carrega o stylesheet CSS externo e vincula as fontes tipográficas."""
    css_full_path = os.path.join(os.path.dirname(__file__), css_rel_path)
    if os.path.exists(css_full_path):
        with open(css_full_path, "r", encoding="utf-8") as f:
            css_rules = f.read()
        st.html(
            f"""
            <link rel="preconnect" href="https://fonts.googleapis.com">
            <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
            <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
            <style>
            {css_rules}
            </style>
            """
        )

load_css()

# Header Superior Moderno
st.html(
    """
    <div class="app-header-container">
        <div class="header-status-pill">
            <span class="header-status-dot"></span>
            <span>SISTEMA OPERACIONAL • BROBOT</span>
        </div>
        <h1 class="app-main-title">Central de Erros</h1>
        <p class="app-sub-title">Automação de saneamento de dados, comunicação com clientes e integração WhatsApp.</p>
    </div>
    """
)

# Barra Lateral: Gestão de Contatos WhatsApp
with st.sidebar:
    st.html(
        """
        <div class="sidebar-header-box">
            <div class="sidebar-header-title">Destinos WhatsApp</div>
            <div class="sidebar-header-sub">Gerencie grupos e contatos individuais para envio direto.</div>
        </div>
        """
    )
    
    with st.expander("Cadastrar / Editar Contato", expanded=False, icon=":material/person_add:"):
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
        
        if st.button("Salvar Destino", icon=":material/save:", use_container_width=True):
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
        with st.expander(f"Destinos Cadastrados ({len(contatos_cadastrados)})", expanded=False, icon=":material/contacts:"):
            for cli, info in list(contatos_cadastrados.items()):
                tipo = info.get("contact_type", "group_name")
                c_tipo_label = "Grupo" if tipo == "group_name" else "Telefone" if tipo == "phone" else "Link"
                st.markdown(f"**{cli}**  \n`{c_tipo_label}: {info['contact_value']}`")
                if st.button(f"Remover {cli}", icon=":material/delete:", key=f"del_{cli}"):
                    delete_client_contact(cli)
                    st.rerun()
                st.write("---")
    else:
        st.info("Nenhum grupo ou contato cadastrado ainda.", icon=":material/info:")

    st.divider()
    st.html(
        """
        <div class="cooldown-sidebar-card">
            <div class="cooldown-sidebar-header">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
                <span>Cooldown Automático</span>
            </div>
            <div class="cooldown-sidebar-body">
                Bloqueio de reenvio do mesmo erro configurado para <b>1 dia (24h)</b> por cliente.
            </div>
        </div>
        """
    )

# Funções de Renderização de Botões (Copy e WhatsApp)
def render_action_buttons(text_to_copy: str, client_id: str, contact_info: Optional[Dict[str, str]]):
    """Renderiza os botões de ação nativos: Copiar Mensagem e Abrir WhatsApp (sem iframes)."""
    c_type = contact_info.get("contact_type") if contact_info else None
    c_val = contact_info.get("contact_value", "") if contact_info else ""

    if c_type == "phone":
        col_c, col_w = st.columns([1, 1])
        with col_c:
            if st.button("Copiar Mensagem", icon=":material/content_copy:", key=f"btn_cp_{client_id}", use_container_width=True):
                pyperclip.copy(text_to_copy)
                st.toast("Mensagem copiada para a área de transferência!", icon=":material/check_circle:")
        with col_w:
            encoded_msg = urllib.parse.quote(text_to_copy)
            wa_url = f"https://wa.me/{c_val}?text={encoded_msg}"
            st.link_button("Abrir no WhatsApp", icon=":material/chat:", url=wa_url, use_container_width=True)

    elif c_type == "group_link":
        col_c, col_w = st.columns([1, 1])
        with col_c:
            if st.button("Copiar Mensagem", icon=":material/content_copy:", key=f"btn_cp_{client_id}", use_container_width=True):
                pyperclip.copy(text_to_copy)
                st.toast("Mensagem copiada para a área de transferência!", icon=":material/check_circle:")
        with col_w:
            st.link_button("Abrir Grupo WhatsApp", icon=":material/groups:", url=c_val, use_container_width=True)

    else:
        if st.button("Copiar Mensagem", icon=":material/content_copy:", key=f"btn_cp_{client_id}", use_container_width=True):
            pyperclip.copy(text_to_copy)
            st.toast("Mensagem copiada para a área de transferência!", icon=":material/check_circle:")


@st.cache_data(show_spinner=False)
def load_and_process_excel_cached(file_bytes: bytes):
    """Lê, valida, processa e prepara mensagens a partir dos bytes do arquivo Excel com cache."""
    from io import BytesIO
    df = pd.read_excel(BytesIO(file_bytes), engine="openpyxl")
    is_valid, missing_columns = validate_columns(df)
    if not is_valid:
        return df, False, missing_columns, {}, [], {}, {}
    dados, erros_sem_template = process_dataframe(df)
    mensagens = build_messages(dados)
    contagem_registros = count_errors_by_account(df)
    return df, True, [], dados, erros_sem_template, mensagens, contagem_registros


@st.cache_data(show_spinner=False)
def get_cached_account_excel(file_hash: str, cliente: str, _dataframe: pd.DataFrame) -> bytes:
    """Gera e armazena em cache o arquivo Excel para download de um cliente específico."""
    return export_account_errors_to_excel(_dataframe, cliente)


def toggle_enviado(cliente: str, chk_res_key: str, erros_do_cliente: List[str]):
    """Callback instantâneo ao alternar o checkbox de Enviado."""
    chk_env_key = f"chk_env_{cliente}"
    val = st.session_state.get(chk_env_key, False)
    st.session_state.enviados[cliente] = val
    if val:
        st.session_state.resolvidos[cliente] = False
        st.session_state[chk_res_key] = False
        register_client_all_errors_sent(cliente, erros_do_cliente, channel="whatsapp")


def toggle_resolvido(cliente: str, chk_env_key: str, erros_do_cliente: List[str]):
    """Callback instantâneo ao alternar o checkbox de Resolvido."""
    chk_res_key = f"chk_res_{cliente}"
    val = st.session_state.get(chk_res_key, False)
    st.session_state.resolvidos[cliente] = val
    if val:
        st.session_state.enviados[cliente] = False
        st.session_state[chk_env_key] = False
        register_client_all_errors_sent(cliente, erros_do_cliente, channel="resolvido")


def render_operacional_tab():
    # 1. Campo Obrigatório: Data da análise / Data do Daily
    col_up_date, col_up_file = st.columns([1.3, 2.7])
    with col_up_date:
        data_analise = st.date_input(
            "Data da Análise",
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
        st.info("Aguardando envio da planilha. Defina a data da análise e selecione um arquivo para começar.", icon=":material/upload_file:")
    else:
        file_bytes = uploaded_file.getvalue()
        file_hash = compute_file_hash(file_bytes)
        try:
            dataframe, is_valid, missing_columns, dados, erros_sem_template, mensagens, contagem_registros = (
                load_and_process_excel_cached(file_bytes)
            )
        except Exception as exc:
            st.error(f"Erro ao ler o arquivo Excel: {exc}", icon=":material/error:")
        else:
            if not is_valid:
                st.error(
                    "**Planilha inválida.** As seguintes colunas obrigatórias estão ausentes:\n\n"
                    + "\n".join([f"• `{col}`" for col in missing_columns]),
                    icon=":material/error:"
                )
            else:
                target_date_str = data_analise.strftime("%Y-%m-%d")
                target_date_fmt = data_analise.strftime("%d/%m/%Y")

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
                        st.info(f"Substituição cancelada para **{target_date_fmt}**. Os dados históricos anteriores foram preservados.", icon=":material/info:")
                    else:
                        # Exibir alerta claro com botões de confirmação
                        orig_file = existing_snap.get("file_name", "planilha anterior")
                        orig_tot = existing_snap.get("total_erros", 0)
                        st.warning(
                            f"**Já existe um histórico salvo para {target_date_fmt}.**\n\n"
                            f"• Histórico atual: arquivo `{orig_file}` ({orig_tot} erros)\n\n"
                            f"Se você continuar, os dados desse dia serão **substituídos** pelo arquivo atual (`{uploaded_file.name}`).",
                            icon=":material/warning:"
                        )
                        col_c, col_s = st.columns([1, 1.8])
                        with col_c:
                            if st.button("Cancelar", icon=":material/close:", key=f"btn_cancel_{target_date_str}_{file_hash}"):
                                st.session_state[cancel_key] = True
                                st.session_state[replace_key] = False
                                st.rerun()
                        with col_s:
                            if st.button("Substituir dados", icon=":material/sync:", type="primary", key=f"btn_subst_{target_date_str}_{file_hash}"):
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

                # Gravação independente e complementar do histórico por cliente (baseado na coluna 'Data Consulta')
                client_history_key = f"client_hist_{file_hash}"
                if st.session_state.get("last_client_history_key") != client_history_key:
                    try:
                        record_client_history(dataframe, file_hash=file_hash, force_replace=True)
                        st.session_state["last_client_history_key"] = client_history_key
                    except Exception:
                        pass

                st.divider()

                # Pré-calcular histórico de duplicidades/cooldown por cliente (consulta única otimizada)
                recent_cooldowns = get_all_recent_cooldowns(days=COOLDOWN_DAYS)
                duplicidades_por_cliente = {}
                for cliente in mensagens:
                    erros_cli = list(dados.get(cliente, {}).keys())
                    duplicidades_por_cliente[cliente] = {
                        err: recent_cooldowns[(cliente, err)]
                        for err in erros_cli
                        if (cliente, err) in recent_cooldowns
                    }

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

                # Resumo em Métricas Modernas com Ícones Vetoriais
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.html(
                        f"""
                        <div class="metric-card">
                            <div class="metric-top">
                                <span class="metric-label">Total de Clientes</span>
                                <div class="metric-icon-box icon-indigo">
                                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>
                                </div>
                            </div>
                            <div class="metric-value">{total_clientes}</div>
                            <div class="metric-footer">Contas identificadas na planilha</div>
                        </div>
                        """
                    )
                with col2:
                    pct_conc = (total_concluidos / total_clientes * 100) if total_clientes > 0 else 0
                    st.html(
                        f"""
                        <div class="metric-card">
                            <div class="metric-top">
                                <span class="metric-label">Progresso Concluído</span>
                                <div class="metric-icon-box icon-emerald">
                                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
                                </div>
                            </div>
                            <div class="metric-value">{total_concluidos} <span class="metric-denom">/ {total_clientes}</span></div>
                            <div class="metric-footer">{pct_conc:.0f}% das contas tratadas ou em cooldown</div>
                        </div>
                        """
                    )
                with col3:
                    st.html(
                        f"""
                        <div class="metric-card">
                            <div class="metric-top">
                                <span class="metric-label">Tipos de Erros</span>
                                <div class="metric-icon-box icon-amber">
                                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                                </div>
                            </div>
                            <div class="metric-value">{total_erros_unicos}</div>
                            <div class="metric-footer">Categorias de ocorrências mapeadas</div>
                        </div>
                        """
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
                        st.caption(f"**Histórico Daily{dt_label}:** {msg_s} *(Acesse a aba Acompanhamento Daily para filtrar e analisar)*")
                    else:
                        st.warning(f"**Histórico Daily{dt_label}:** {msg_s}", icon=":material/warning:")

                st.write("")

                # Pesquisa e Filtro por Cliente
                termo_pesquisa = st.text_input("Pesquisar Cliente", placeholder="Digite o nome da conta ou cliente...")

                clientes_filtrados = [
                    cliente for cliente in mensagens 
                    if not termo_pesquisa or termo_pesquisa.lower() in cliente.lower()
                ]

                st.write("")

                if not clientes_filtrados:
                    st.warning("Nenhum cliente encontrado com esse termo de busca.", icon=":material/search_off:")
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

                        # Buscar contato / nome de grupo cadastrado (em memória)
                        contact_info = contatos_cadastrados.get(cliente)

                        # Status e Ícone do Card
                        if is_enviado:
                            status_tag = " • [ENVIADO]"
                            card_icon = ":material/check_circle:"
                        elif is_resolvido:
                            status_tag = " • [RESOLVIDO]"
                            card_icon = ":material/task_alt:"
                        elif tem_resolvido:
                            status_tag = " • [RESOLVIDO RECENTE]"
                            card_icon = ":material/task_alt:"
                        elif tem_notificado:
                            status_tag = " • [COOLDOWN ATIVO]"
                            card_icon = ":material/schedule:"
                        else:
                            status_tag = ""
                            card_icon = ":material/business:"

                        plural_s = "s" if qtd_erros > 1 else ""
                        expander_label = f"{cliente} ({qtd_erros} tipo{plural_s} de erro){status_tag}"

                        with st.expander(expander_label, icon=card_icon):
                            # Alerta se houver erro já resolvido recentemente (1 dia)
                            if tem_resolvido:
                                st.html(
                                    """
                                    <div class="resolved-alert">
                                        <div class="alert-icon-box">
                                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
                                        </div>
                                        <div>
                                            <div class="alert-title">Resolvido Recentemente</div>
                                            <div class="alert-desc">Este erro já foi marcado como resolvido para este cliente:</div>
                                        </div>
                                    </div>
                                    """
                                )
                                for err_nome, data_envio in erros_resolvidos_ant.items():
                                    try:
                                        dt_fmt = datetime.strptime(data_envio, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y às %H:%M")
                                    except Exception:
                                        dt_fmt = data_envio
                                    st.caption(f"• **{err_nome}** (resolvido em {dt_fmt})")

                            # Alerta se houver erro já enviado recentemente (1 dia)
                            if tem_notificado:
                                st.html(
                                    """
                                    <div class="cooldown-alert">
                                        <div class="alert-icon-box">
                                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                                        </div>
                                        <div>
                                            <div class="alert-title">Cooldown Ativo (24 Horas)</div>
                                            <div class="alert-desc">Este cliente já recebeu notificação recente para:</div>
                                        </div>
                                    </div>
                                    """
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
                                    "Grupo WhatsApp" if c_type == "group_name"
                                    else "Telefone" if c_type == "phone"
                                    else "Link do Grupo"
                                )
                                st.html(
                                    f"""
                                    <div class="contact-badge">
                                        <div class="contact-badge-left">
                                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>
                                            <span><b>{c_tipo_label}:</b></span>
                                            <code>{contact_info['contact_value']}</code>
                                        </div>
                                        <span class="badge-status-dot"></span>
                                    </div>
                                    """
                                )
                            else:
                                st.caption("Grupo ou contato do WhatsApp ainda não cadastrado para este cliente.")
                                with st.expander("Vincular Nome do Grupo no WhatsApp", expanded=False, icon=":material/group_add:"):
                                    quick_nome_grupo = st.text_input(
                                        "Nome do Grupo no WhatsApp",
                                        key=f"quick_g_{cliente}_{index}",
                                        placeholder="Ex: Suporte - Frota ABC"
                                    )
                                    if st.button("Salvar Grupo", icon=":material/save:", key=f"btn_save_{cliente}_{index}"):
                                        if quick_nome_grupo:
                                            ok, msg = save_client_contact(cliente, quick_nome_grupo, "group_name")
                                            if ok:
                                                st.success(msg)
                                                st.rerun()
                                            else:
                                                st.error(msg)

                            # Checkboxes de Controle lado a lado (com callbacks instantâneos)
                            col_env, col_res = st.columns(2)

                            chk_env_key = f"chk_env_{cliente}"
                            chk_res_key = f"chk_res_{cliente}"

                            if chk_env_key not in st.session_state:
                                st.session_state[chk_env_key] = is_enviado
                            if chk_res_key not in st.session_state:
                                st.session_state[chk_res_key] = is_resolvido

                            with col_env:
                                st.checkbox(
                                    "Enviado ao cliente",
                                    key=chk_env_key,
                                    on_change=toggle_enviado,
                                    args=(cliente, chk_res_key, erros_do_cliente),
                                )
                            with col_res:
                                st.checkbox(
                                    "Marcado como Resolvido",
                                    key=chk_res_key,
                                    on_change=toggle_resolvido,
                                    args=(cliente, chk_env_key, erros_do_cliente),
                                )

                            # Área de texto com a mensagem
                            st.text_area(
                                label="Mensagem Pronta",
                                value=mensagem,
                                height=250,
                                key=f"msg_{cliente}_{index}",
                                label_visibility="collapsed"
                            )

                            # Botão de Exportação Excel (contas com mais de 10 registros, com cache)
                            qtd_registros_conta = contagem_registros.get(cliente, 0)
                            if qtd_registros_conta > 10:
                                excel_bytes = get_cached_account_excel(file_hash, cliente, dataframe)
                                nome_arquivo = f"{sanitize_filename(cliente)} - Erros de usuários.xlsx"
                                st.download_button(
                                    label=f"Exportar Excel ({qtd_registros_conta} registros)",
                                    icon=":material/download:",
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
                                        "Abrir no WhatsApp Desktop",
                                        icon=":material/desktop_windows:",
                                        key=f"btn_wa_desk_{cliente}_{index}",
                                        type="primary",
                                        use_container_width=True,
                                        help=f"Abre o WhatsApp Desktop, pesquisa por '{nome_grupo_alvo}', entra na conversa e já cola o texto na caixa de envio.",
                                    ):
                                        with st.spinner(f"Localizando '{nome_grupo_alvo}' no WhatsApp Desktop..."):
                                            ok_desk, msg_desk = open_group_in_whatsapp_desktop(nome_grupo_alvo, mensagem)
                                            if ok_desk:
                                                st.toast(msg_desk, icon=":material/check_circle:")
                                            else:
                                                st.error(msg_desk, icon=":material/error:")

                                with col_btn_copy:
                                    render_action_buttons(mensagem, client_id=f"cli_{index}", contact_info=contact_info)
                            else:
                                render_action_buttons(mensagem, client_id=f"cli_{index}", contact_info=contact_info)

                # Avisos de Erros sem Template (Discreto no final)
                if erros_sem_template:
                    st.write("")
                    with st.expander("Erros pendentes de cadastro de template", icon=":material/warning:"):
                        st.write("Os seguintes erros foram encontrados na planilha mas não possuem template cadastrado no sistema:")
                        for erro in erros_sem_template:
                            st.write(f"• `{erro}`")


# Navegação Principal em Abas
tab_operacional, tab_acompanhamento, tab_cliente = st.tabs([
    "Operacional (Envio)", 
    "Acompanhamento Daily", 
    "Análise por Cliente"
])

with tab_operacional:
    render_operacional_tab()

with tab_acompanhamento:
    render_acompanhamento_tab()

with tab_cliente:
    render_cliente_tab()
