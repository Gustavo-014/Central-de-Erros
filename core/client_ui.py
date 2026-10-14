from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from core.client_db import (
    get_all_history_clients,
    get_client_available_dates,
    get_client_consulta_details,
    get_client_consultas_history,
    get_client_error_ranking,
    get_client_evolution,
    get_client_summary,
)


def _format_date_br(iso_date: str) -> str:
    """Formata ISO 'YYYY-MM-DD' para 'DD/MM/YYYY'."""
    try:
        dt = datetime.strptime(iso_date, "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return iso_date


def render_cliente_tab() -> None:
    """Renderiza a interface completa da aba Análise por Cliente."""
    clientes_disponiveis = get_all_history_clients()

    if not clientes_disponiveis:
        st.html(
            """
            <div class="empty-state-card">
                <div class="empty-state-icon">
                    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
                </div>
                <div class="empty-state-title">Nenhum histórico de cliente registrado ainda</div>
                <div class="empty-state-desc">
                    Para iniciar o histórico por cliente, acesse a aba <b>Operacional (Envio)</b> e importe uma planilha de erros
                    contendo a coluna <b>Data Consulta</b>. O sistema registrará automaticamente os dados históricos para cada cliente.
                </div>
            </div>
            """
        )
        return

    st.markdown("### Análise por Cliente")
    st.caption("Investigação histórica individual do comportamento de cada conta ao longo das consultas.")

    # -------------------------------------------------------------------------
    # 1. FILTRO DE CLIENTE
    # -------------------------------------------------------------------------
    col_sel, col_info = st.columns([2.5, 2.5])
    with col_sel:
        cliente_selecionado = st.selectbox(
            "Selecione o Cliente:",
            options=clientes_disponiveis,
            index=0,
            key="client_analysis_selectbox",
            help="Escolha o cliente/conta para consultar todo o histórico disponível.",
        )

    with col_info:
        total_clientes = len(clientes_disponiveis)
        st.html(
            f"""
            <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 10px 14px; font-size: 0.85rem; color: #94a3b8; margin-top: 14px;">
                <div><b>Base de Clientes:</b> <span style="color: #f1f5f9;">{total_clientes} cliente{'s' if total_clientes > 1 else ''} com histórico registrado</span></div>
            </div>
            """
        )

    if not cliente_selecionado:
        st.info("Selecione um cliente para visualizar o histórico.", icon=":material/info:")
        return

    # Buscar dados do cliente selecionado
    summary = get_client_summary(cliente_selecionado)
    history = get_client_consultas_history(cliente_selecionado)
    ranking = get_client_error_ranking(cliente_selecionado)
    evolution = get_client_evolution(cliente_selecionado)
    available_dates = get_client_available_dates(cliente_selecionado)

    st.write("")

    # -------------------------------------------------------------------------
    # 2. BLOCO DE RESUMO (CARDS DE MÉTRICAS MODERNOS)
    # -------------------------------------------------------------------------
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.html(
            f"""
            <div class="metric-card">
                <div class="metric-top">
                    <span class="metric-label">Total Consultas</span>
                    <div class="metric-icon-box icon-indigo">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
                    </div>
                </div>
                <div class="metric-value">{summary['total_consultas']}</div>
                <div class="metric-footer">Registros independentes</div>
            </div>
            """
        )
    with c2:
        st.html(
            f"""
            <div class="metric-card">
                <div class="metric-top">
                    <span class="metric-label">Primeira Consulta</span>
                    <div class="metric-icon-box icon-sky">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 14 14"></polyline></svg>
                    </div>
                </div>
                <div class="metric-value" style="font-size: 1.45rem;">{summary['primeira_consulta']}</div>
                <div class="metric-footer">Data inicial da conta</div>
            </div>
            """
        )
    with c3:
        st.html(
            f"""
            <div class="metric-card">
                <div class="metric-top">
                    <span class="metric-label">Última Consulta</span>
                    <div class="metric-icon-box icon-emerald">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
                    </div>
                </div>
                <div class="metric-value" style="font-size: 1.45rem;">{summary['ultima_consulta']}</div>
                <div class="metric-footer">Data mais recente</div>
            </div>
            """
        )
    with c4:
        st.html(
            f"""
            <div class="metric-card">
                <div class="metric-top">
                    <span class="metric-label">Total de Erros</span>
                    <div class="metric-icon-box icon-rose">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                    </div>
                </div>
                <div class="metric-value" style="color: #fda4af;">{summary['total_erros']}</div>
                <div class="metric-footer">Volume acumulado</div>
            </div>
            """
        )

    st.divider()

    # -------------------------------------------------------------------------
    # 3. HISTÓRICO DE CONSULTAS & PRINCIPAIS ERROS (LADO A LADO)
    # -------------------------------------------------------------------------
    col_hist, col_rank = st.columns([1.1, 1.1])

    with col_hist:
        st.markdown("#### Histórico de Consultas")
        if history:
            df_hist = pd.DataFrame([
                {
                    "Data Consulta": item["data_consulta"],
                    "Quantidade de erros": item["total_erros"],
                    "Erros encontrados": item["erros_resumo"],
                }
                for item in history
            ])
            st.dataframe(
                df_hist,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Nenhuma consulta registrada para este cliente.", icon=":material/info:")

    with col_rank:
        st.markdown("#### Principais Erros (Ranking)")
        if ranking:
            df_rank = pd.DataFrame([
                {
                    "Erro": r["erro"],
                    "Ocorrências": r["total_ocorrencias"],
                    "% Total": f"{r['percentual']:.1f}%",
                    "Tipo": "Consulta" if r["tipo"] == "consulta" else "Usuário" if r["tipo"] == "usuario" else "Não classificado",
                }
                for r in ranking
            ])
            st.dataframe(
                df_rank,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Nenhum erro registrado para este cliente.", icon=":material/info:")

    st.divider()

    # -------------------------------------------------------------------------
    # 4. EVOLUÇÃO AO LONGO DO TEMPO (GRÁFICO)
    # -------------------------------------------------------------------------
    st.markdown("#### Evolução ao Longo do Tempo")
    st.caption("Acompanhe como a quantidade de erros deste cliente está variando ao longo das consultas.")

    if evolution:
        df_evo = pd.DataFrame([
            {
                "Data": e["data_consulta"],
                "Total de Erros": e["total_erros"],
                "Erros de Usuário": e["erros_usuario"],
                "Erros de Consulta": e["erros_consulta"],
            }
            for e in evolution
        ])

        # Se houver mais de uma data, desenha o gráfico de linha / barra
        tab_g1, tab_g2 = st.tabs(["Total de Erros", "Por Categoria de Erro"])
        
        with tab_g1:
            st.line_chart(
                df_evo.set_index("Data")[["Total de Erros"]],
                use_container_width=True,
            )

        with tab_g2:
            st.bar_chart(
                df_evo.set_index("Data")[["Erros de Usuário", "Erros de Consulta"]],
                use_container_width=True,
            )
    else:
        st.info("Dados de evolução não disponíveis.", icon=":material/info:")

    st.divider()

    # -------------------------------------------------------------------------
    # 5. DETALHAMENTO POR CONSULTA ESPECÍFICA
    # -------------------------------------------------------------------------
    st.markdown("#### Detalhamento por Consulta")
    st.caption("Selecione uma data para inspecionar os erros específicos e indicadores daquela rodada.")

    if available_dates:
        col_date_sel, _ = st.columns([2, 3])
        with col_date_sel:
            selected_date = st.selectbox(
                "Selecione a Data da Consulta:",
                options=available_dates,
                index=0,
                format_func=_format_date_br,
                key="client_history_detail_date_select",
            )

        if selected_date:
            details = get_client_consulta_details(cliente_selecionado, selected_date)
            date_fmt = _format_date_br(selected_date)
            total_erros_rodada = sum(d["quantidade"] for d in details)

            st.html(
                f"""
                <div style="background: rgba(15, 23, 42, 0.65); border: 1px solid rgba(99, 102, 241, 0.22); border-radius: 10px; padding: 12px 18px; margin-bottom: 16px; font-size: 0.92rem;">
                    <span style="color: #94a3b8;">Cliente:</span> <b style="color: #f8fafc;">{cliente_selecionado}</b> &nbsp;|&nbsp; 
                    <span style="color: #94a3b8;">Data:</span> <b style="color: #f8fafc;">{date_fmt}</b> &nbsp;|&nbsp; 
                    <span style="color: #94a3b8;">Total de Erros nesta Consulta:</span> <b style="color: #818cf8;">{total_erros_rodada}</b>
                </div>
                """
            )

            if details:
                for d in details:
                    erro_title = d["erro"]
                    qtd = d["quantidade"]
                    tipo_badge = (
                        "Consulta" if d["tipo"] == "consulta"
                        else "Usuário" if d["tipo"] == "usuario"
                        else "Não classificado"
                    )
                    indicadores = d.get("indicadores") or []

                    with st.expander(f"{erro_title} • {qtd} ocorrência{'s' if qtd != 1 else ''} ({tipo_badge})", expanded=False, icon=":material/error_outline:"):
                        if indicadores:
                            st.caption(f"Identificadores afetados ({len(indicadores)}):")
                            # Exibir em grade ou chips
                            ind_cols = st.columns(3)
                            for idx, ind in enumerate(indicadores):
                                ind_cols[idx % 3].code(ind, language=None)
                        else:
                            st.caption("Nenhum identificador específico registrado para esta ocorrência.")
            else:
                st.info("Nenhum detalhe encontrado para esta data.", icon=":material/info:")
    else:
        st.info("Nenhuma data disponível para detalhamento.", icon=":material/info:")
