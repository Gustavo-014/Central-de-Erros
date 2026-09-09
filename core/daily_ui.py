from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from core.daily_db import (
    delete_snapshot_by_date,
    get_available_dates,
    get_client_errors,
    get_client_evolution,
    get_client_ranking,
    get_comparison_data,
    get_period_data,
    get_recurrent_errors,
    get_snapshot_by_date,
    get_snapshots_evolution,
    get_top_errors,
)
from core.daily_service import (
    get_daily_answers_comparison,
    get_daily_answers_period,
    get_daily_answers_single,
)


def _format_date_option(d_str: str) -> str:
    """Formata a data ISO para DD/MM/YYYY com indicação do dia da semana."""
    try:
        dt = datetime.strptime(d_str, "%Y-%m-%d")
        dias_semana = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        return f"{dt.strftime('%d/%m/%Y')} ({dias_semana[dt.weekday()]})"
    except Exception:
        return d_str


def _format_delta_badge(delta_abs: Optional[int], delta_pct: Optional[float]) -> str:
    """Formata texto e cor de delta para exibição visual de variações."""
    if delta_abs is None or delta_pct is None:
        return "—"
    if delta_abs > 0:
        return f"🔺 +{delta_abs} (+{delta_pct:.1f}%)"
    if delta_abs < 0:
        return f"🔽 {delta_abs} ({delta_pct:.1f}%)"
    return "= 0 (0.0%)"


def render_acompanhamento_tab() -> None:
    """Renderiza a interface completa da aba 📊 Acompanhamento com 3 modos de análise."""
    available_dates = get_available_dates()

    if not available_dates:
        st.markdown(
            """
            <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 12px; padding: 24px; text-align: center; margin-top: 20px;">
                <h3 style="color: #c084fc; margin-bottom: 8px;">📭 Nenhum snapshot diário registrado ainda</h3>
                <p style="color: #cbd5e1; font-size: 1rem; margin-bottom: 0;">
                    Para iniciar o histórico de Acompanhamento / Daily, acesse a aba <b>⚡ Operacional</b> e importe uma planilha de erros.
                    O sistema registrará automaticamente o snapshot com a data de incidência no banco SQLite.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # -------------------------------------------------------------------------
    # CONTROLES SUPERIORES: MODO DE ANÁLISE E FILTROS DE DATAS
    # -------------------------------------------------------------------------
    st.markdown("### 📊 Acompanhamento / Daily")

    col_mode, col_info = st.columns([2.5, 2.5])
    with col_mode:
        modo_analise = st.radio(
            "**Modo de análise:**",
            options=["Um dia", "Comparar datas", "Período"],
            index=0,
            horizontal=True,
            key="daily_mode_radio",
        )

    with col_info:
        total_snaps = len(available_dates)
        mais_antigo = _format_date_option(available_dates[-1])
        mais_recente = _format_date_option(available_dates[0])
        st.markdown(
            f"""
            <div style="padding-top: 8px; font-size: 0.86rem; color: #94a3b8;">
                📚 <b>Histórico disponível:</b> {total_snaps} dia{'s' if total_snaps > 1 else ''} registrado{'s' if total_snaps > 1 else ''}<br>
                📅 De <code>{mais_antigo}</code> até <code>{mais_recente}</code>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")

    # =========================================================================
    # MODO 1: UM DIA (Sem comparação automática com dia anterior)
    # =========================================================================
    if modo_analise == "Um dia":
        col_f1, col_f2 = st.columns([1.5, 3.5])
        with col_f1:
            selected_date = st.selectbox(
                "📅 **Data analisada:**",
                options=available_dates,
                index=0,
                format_func=_format_date_option,
                key="daily_single_date",
            )

        snap = get_snapshot_by_date(selected_date)
        if not snap:
            st.warning("Não foi possível carregar os dados para a data selecionada.")
            return

        with col_f2:
            file_orig = snap.get("file_name") or "Planilha importada"
            created_at = snap.get("created_at") or ""
            st.markdown(
                f"""
                <div style="padding-top: 26px; font-size: 0.88rem; color: #94a3b8;">
                    📄 Origem: <code>{file_orig}</code> &nbsp;|&nbsp; 🕒 Processado em: <code>{created_at}</code>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Alerta se houver erros não classificados
        erros_nc = snap.get("erros_nao_classificados", 0)
        if erros_nc > 0:
            st.warning(
                f"⚠️ **Atenção:** Há **{erros_nc}** ocorrência(s) de erro(s) **não classificados** nesta data. "
                f"Eles foram computados separadamente e podem ser categorizados em `data/templates.json`."
            )

        snapshot_id = snap["id"]
        client_ranking = get_client_ranking(snapshot_id)
        top_errors = get_top_errors(snapshot_id)

        st.write("")

        # BLOCO 1: PANORAMA GERAL
        st.markdown("#### 1. 📌 Panorama Geral")
        st.caption("Visão estrita dos indicadores da data selecionada (sem comparações automáticas).")
        p1, p2, p3, p4 = st.columns(4)
        with p1:
            st.metric("Total de Erros", snap["total_erros"], help="Volume total de ocorrências de erros na planilha desta data.")
        with p2:
            st.metric("Erros de Consulta", snap["erros_consulta"], help="Erros gerados por instabilidades em portais, consultas ou sistemas.")
        with p3:
            st.metric("Erros de Usuário", snap["erros_usuario"], help="Erros operacionais ou acionáveis dependentes de intervenção com o cliente.")
        with p4:
            st.metric("Clientes Afetados", snap["clientes_afetados"], help="Total de clientes distintos que tiveram pelo menos 1 erro nesta data.")

        st.divider()

        # BLOCO 2: EVOLUÇÃO DIÁRIA
        st.markdown("#### 2. 📈 Contexto Histórico Diário")
        history_records = get_snapshots_evolution()
        if history_records:
            df_hist = pd.DataFrame(history_records)
            df_chart = pd.DataFrame(
                {
                    "Data": df_hist["data"].apply(lambda d: datetime.strptime(d, "%Y-%m-%d").strftime("%d/%m")),
                    "Total de Erros": df_hist["total_erros"],
                    "Consulta": df_hist["erros_consulta"],
                    "Usuário": df_hist["erros_usuario"],
                }
            ).set_index("Data")
            st.line_chart(df_chart, height=280)
        else:
            st.info("Histórico insuficiente para gerar gráfico.")

        st.divider()

        # BLOCO 3: CONCENTRAÇÃO POR CLIENTE
        st.markdown("#### 3. 👥 Concentração por Cliente")
        st.caption(f"Clientes com erros na data {_format_date_option(selected_date)}.")
        if client_ranking:
            df_cli = pd.DataFrame(
                [
                    {
                        "Cliente": c["cliente"],
                        "Total de Erros": c["total_erros"],
                        "Erros Consulta": c["erros_consulta"],
                        "Erros Usuário": c["erros_usuario"],
                        "Não Classificados": c["erros_nao_classificados"],
                        "Representatividade": f"{(c['total_erros'] / snap['total_erros'] * 100.0):.1f}%" if snap['total_erros'] > 0 else "0.0%",
                    }
                    for c in client_ranking
                ]
            )
            st.dataframe(df_cli, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum cliente com erros nesta data.")

        st.divider()

        # BLOCO 4: DETALHAMENTO DO CLIENTE
        st.markdown("#### 4. 🔍 Detalhamento do Cliente")
        if client_ranking:
            client_names = [c["cliente"] for c in client_ranking]
            selected_client = st.selectbox("Selecione um cliente para inspecionar:", options=client_names, key="single_client_select")
            cli_data = next((c for c in client_ranking if c["cliente"] == selected_client), None)

            if cli_data:
                dc1, dc2, dc3, dc4 = st.columns(4)
                with dc1:
                    st.metric("Total do Cliente", cli_data["total_erros"])
                with dc2:
                    st.metric("Erros Consulta", cli_data["erros_consulta"])
                with dc3:
                    st.metric("Erros Usuário", cli_data["erros_usuario"])
                with dc4:
                    st.metric("Não Classificados", cli_data["erros_nao_classificados"])

                col_cevo, col_ctab = st.columns([1.2, 1.8])
                with col_cevo:
                    st.markdown("##### 📈 Histórico deste Cliente")
                    cli_evo = get_client_evolution(selected_client)
                    if cli_evo and len(cli_evo) > 1:
                        df_cevo = pd.DataFrame(cli_evo)
                        df_cchart = pd.DataFrame(
                            {
                                "Data": df_cevo["data"].apply(lambda d: datetime.strptime(d, "%Y-%m-%d").strftime("%d/%m")),
                                "Total": df_cevo["total_erros"],
                            }
                        ).set_index("Data")
                        st.line_chart(df_cchart, height=200)
                    else:
                        st.caption("ℹ️ Apenas 1 registro diário disponível para este cliente.")

                with col_ctab:
                    st.markdown("##### 📋 Erros Deste Cliente")
                    cli_errs = get_client_errors(snapshot_id, selected_client)
                    if cli_errs:
                        df_cerrs = pd.DataFrame(
                            [
                                {
                                    "Erro": e["erro"],
                                    "Tipo": "🔍 Consulta" if e["tipo"] == "consulta" else "👤 Usuário" if e["tipo"] == "usuario" else "❓ Não Classificado",
                                    "Ocorrências": e["quantidade"],
                                }
                                for e in cli_errs
                            ]
                        )
                        st.dataframe(df_cerrs, use_container_width=True, hide_index=True)
                    else:
                        st.info("Nenhum detalhe de erro encontrado.")

        st.divider()

        # BLOCO 5: PRINCIPAIS ERROS
        st.markdown("#### 5. ⚠️ Principais Erros no Dia")
        if top_errors:
            df_top = pd.DataFrame(
                [
                    {
                        "Erro": te["erro"],
                        "Tipo": "🔍 Consulta" if te["tipo"] == "consulta" else "👤 Usuário" if te["tipo"] == "usuario" else "❓ Não Classificado",
                        "Total Ocorrências": te["total_quantidade"],
                        "Clientes Afetados": te["clientes_afetados"],
                    }
                    for te in top_errors
                ]
            )
            st.dataframe(df_top, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum erro registrado.")

        st.divider()

        # BLOCO 7: RESUMO EXECUTIVO
        st.markdown("#### 7. 📋 Resumo Executivo da Daily")
        answers = get_daily_answers_single(selected_date)
        if answers:
            tot = answers["total_erros"]
            cons = answers["erros_consulta"]
            usr = answers["erros_usuario"]
            afet = answers["clientes_afetados"]
            top_c = answers.get("top_client")
            top_share = answers.get("top_client_share", 0.0)
            t_errs = answers.get("top_errors", [])
            t_rec = answers.get("recurrent_errors", [])

            p_cons = (cons / tot * 100.0) if tot > 0 else 0.0
            p_usr = (usr / tot * 100.0) if tot > 0 else 0.0

            top_c_txt = f"**{top_c['cliente']}** com **{top_c['total_erros']} erros** ({top_share:.1f}% do total do dia)" if top_c else "Nenhum"
            top_e_txt = ", ".join([f"**{e['erro']}** ({e['total_quantidade']}x)" for e in t_errs[:3]]) if t_errs else "Nenhum"
            rec_txt = ", ".join([f"**{e['erro']}** ({e['dias_presente']} dias)" for e in t_rec[:3]]) if t_rec else "Sem problemas recorrentes em múltiplos dias."

            st.markdown(
                f"""
                <div style="background: rgba(17, 24, 39, 0.75); border: 1px solid rgba(139, 92, 246, 0.35); border-radius: 12px; padding: 20px; line-height: 1.8;">
                    <ol style="margin-left: -10px; color: #e2e8f0; font-size: 1.02rem;">
                        <li><b>Volume total na data:</b> <code>{tot} erros</code></li>
                        <li><b>Erros de consulta:</b> <code>{cons} erros</code> ({p_cons:.1f}% do volume)</li>
                        <li><b>Erros de usuário:</b> <code>{usr} erros</code> ({p_usr:.1f}% do volume)</li>
                        <li><b>Clientes impactados:</b> <code>{afet} clientes distintos</code></li>
                        <li><b>Maior concentração:</b> {top_c_txt}</li>
                        <li><b>Principais problemas no dia:</b> {top_e_txt}</li>
                        <li><b>Problemas recorrentes no histórico:</b> {rec_txt}</li>
                    </ol>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # =========================================================================
    # MODO 2: COMPARAR DATAS (date_start < date_end com cálculo date_end - date_start)
    # =========================================================================
    elif modo_analise == "Comparar datas":
        if len(available_dates) < 2:
            st.info("ℹ️ São necessárias ao menos **2 datas com snapshots** registradas para realizar comparações. Importe planilhas de outros dias para habilitar.")
            return

        dates_asc = sorted(available_dates)
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            date_start_input = st.selectbox(
                "📅 **Data Inicial (Base):**",
                options=dates_asc,
                index=0,
                format_func=_format_date_option,
                key="cmp_date_start",
            )
        with col_c2:
            date_end_input = st.selectbox(
                "📅 **Data Final (Comparada):**",
                options=dates_asc,
                index=len(dates_asc) - 1,
                format_func=_format_date_option,
                key="cmp_date_end",
            )

        # Validação obrigatória: datas devem ser diferentes
        if date_start_input == date_end_input:
            st.warning("⚠️ **Atenção:** A Data Inicial e a Data Final devem ser **diferentes** para comparação. Selecione duas datas distintas.")
            return

        # Ajustar para garantir date_start < date_end
        if date_start_input > date_end_input:
            date_start, date_end = date_end_input, date_start_input
            st.info(f"ℹ️ As datas foram organizadas cronologicamente para a comparação: **{_format_date_option(date_start)}** → **{_format_date_option(date_end)}**.")
        else:
            date_start, date_end = date_start_input, date_end_input

        comp = get_comparison_data(date_start, date_end)
        if not comp or comp.get("error"):
            st.error(comp.get("error", "Erro ao comparar datas."))
            return

        start_snap = comp["start"]
        end_snap = comp["end"]
        metrics = comp["metrics"]
        client_vars = comp["client_variations"]
        error_vars = comp["error_variations"]
        risers = comp["risers"]
        fallers = comp["fallers"]

        lbl_start = _format_date_option(date_start)
        lbl_end = _format_date_option(date_end)

        st.markdown(
            f"""
            <div style="background: rgba(30, 41, 59, 0.5); border: 1px solid rgba(139, 92, 246, 0.25); border-radius: 8px; padding: 12px 18px; margin-bottom: 18px; font-size: 0.95rem; color: #cbd5e1;">
                🔍 Comparando variação: <b>{lbl_start}</b> (Base) &nbsp;➔&nbsp; <b>{lbl_end}</b> (Atual). 
                Cálculo: <code>Δ = {lbl_end} - {lbl_start}</code>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # BLOCO 1: PANORAMA COMPARATIVO
        st.markdown("#### 1. 📌 Panorama Comparativo")
        cp1, cp2, cp3, cp4 = st.columns(4)

        with cp1:
            tot_m = metrics["total_erros"]
            delta_str = _format_delta_badge(tot_m["delta_abs"], tot_m["delta_pct"])
            st.markdown(
                f"""
                <div class="metric-card" style="text-align: left; padding: 14px;">
                    <div style="font-size: 0.82rem; color: #94a3b8; text-transform: uppercase;">Total de Erros</div>
                    <div style="font-size: 1.1rem; color: #f1f5f9; margin-top: 4px;">
                        <b>Inicial:</b> {tot_m['start']} &nbsp;|&nbsp; <b>Final:</b> {tot_m['end']}
                    </div>
                    <div style="font-size: 1.02rem; margin-top: 6px; font-weight: bold; color: {'#ef4444' if tot_m['delta_abs'] > 0 else '#10b981' if tot_m['delta_abs'] < 0 else '#cbd5e1'};">
                        {delta_str}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with cp2:
            cons_m = metrics["erros_consulta"]
            delta_str = _format_delta_badge(cons_m["delta_abs"], cons_m["delta_pct"])
            st.markdown(
                f"""
                <div class="metric-card" style="text-align: left; padding: 14px;">
                    <div style="font-size: 0.82rem; color: #94a3b8; text-transform: uppercase;">Erros de Consulta</div>
                    <div style="font-size: 1.1rem; color: #f1f5f9; margin-top: 4px;">
                        <b>Inicial:</b> {cons_m['start']} &nbsp;|&nbsp; <b>Final:</b> {cons_m['end']}
                    </div>
                    <div style="font-size: 1.02rem; margin-top: 6px; font-weight: bold; color: {'#ef4444' if cons_m['delta_abs'] > 0 else '#10b981' if cons_m['delta_abs'] < 0 else '#cbd5e1'};">
                        {delta_str}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with cp3:
            usr_m = metrics["erros_usuario"]
            delta_str = _format_delta_badge(usr_m["delta_abs"], usr_m["delta_pct"])
            st.markdown(
                f"""
                <div class="metric-card" style="text-align: left; padding: 14px;">
                    <div style="font-size: 0.82rem; color: #94a3b8; text-transform: uppercase;">Erros de Usuário</div>
                    <div style="font-size: 1.1rem; color: #f1f5f9; margin-top: 4px;">
                        <b>Inicial:</b> {usr_m['start']} &nbsp;|&nbsp; <b>Final:</b> {usr_m['end']}
                    </div>
                    <div style="font-size: 1.02rem; margin-top: 6px; font-weight: bold; color: {'#ef4444' if usr_m['delta_abs'] > 0 else '#10b981' if usr_m['delta_abs'] < 0 else '#cbd5e1'};">
                        {delta_str}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with cp4:
            cli_m = metrics["clientes_afetados"]
            delta_str = _format_delta_badge(cli_m["delta_abs"], cli_m["delta_pct"])
            st.markdown(
                f"""
                <div class="metric-card" style="text-align: left; padding: 14px;">
                    <div style="font-size: 0.82rem; color: #94a3b8; text-transform: uppercase;">Clientes Afetados</div>
                    <div style="font-size: 1.1rem; color: #f1f5f9; margin-top: 4px;">
                        <b>Inicial:</b> {cli_m['start']} &nbsp;|&nbsp; <b>Final:</b> {cli_m['end']}
                    </div>
                    <div style="font-size: 1.02rem; margin-top: 6px; font-weight: bold; color: {'#ef4444' if cli_m['delta_abs'] > 0 else '#10b981' if cli_m['delta_abs'] < 0 else '#cbd5e1'};">
                        {delta_str}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.divider()

        # BLOCO 2: GRÁFICO COMPARATIVO
        st.markdown("#### 2. 📊 Comparativo Gráfico")
        df_cmp_bars = pd.DataFrame(
            {
                "Indicador": ["Total de Erros", "Erros Consulta", "Erros Usuário", "Clientes Afetados"],
                f"Data Inicial ({date_start})": [tot_m["start"], cons_m["start"], usr_m["start"], cli_m["start"]],
                f"Data Final ({date_end})": [tot_m["end"], cons_m["end"], usr_m["end"], cli_m["end"]],
            }
        ).set_index("Indicador")
        st.bar_chart(df_cmp_bars, height=280)

        st.divider()

        # BLOCO 3: CONCENTRAÇÃO POR CLIENTE (COMPARATIVO)
        st.markdown("#### 3. 👥 Comparação por Cliente")
        st.caption(f"Evolução cliente a cliente entre {date_start} e {date_end}.")
        if client_vars:
            df_cvars = pd.DataFrame(
                [
                    {
                        "Cliente": c["cliente"],
                        f"Erros ({date_start})": c["total_start"],
                        f"Erros ({date_end})": c["total_end"],
                        "Variação (Δ)": f"{c['delta_abs']:+d}",
                        "Variação (%)": f"{c['delta_pct']:+.1f}%",
                        "Situação": "Novo 🚀" if c["is_new"] else "Resolvido 🎉" if c["is_resolved"] else "Aumentou 🔺" if c["delta_abs"] > 0 else "Reduziu 🔽" if c["delta_abs"] < 0 else "Estável =",
                    }
                    for c in client_vars
                ]
            )
            st.dataframe(df_cvars, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum cliente registrado nas datas selecionadas.")

        st.divider()

        # BLOCO 4: DETALHAMENTO DO CLIENTE (COMPARATIVO)
        st.markdown("#### 4. 🔍 Detalhamento do Cliente na Comparação")
        if client_vars:
            cli_names = [c["cliente"] for c in client_vars]
            sel_cli_cmp = st.selectbox("Selecione um cliente para comparar:", options=cli_names, key="cmp_client_select")
            c_info = next((c for c in client_vars if c["cliente"] == sel_cli_cmp), None)

            if c_info:
                st.markdown(
                    f"""
                    <div style="background: rgba(30, 41, 59, 0.6); border-radius: 8px; padding: 12px 18px; margin-bottom: 12px;">
                        <b>Cliente:</b> <code>{sel_cli_cmp}</code><br>
                        <b>{date_start}:</b> {c_info['total_start']} erros &nbsp;|&nbsp; 
                        <b>{date_end}:</b> {c_info['total_end']} erros &nbsp;|&nbsp; 
                        <b>Variação:</b> <span style="color: {'#ef4444' if c_info['delta_abs'] > 0 else '#10b981' if c_info['delta_abs'] < 0 else '#cbd5e1'}; font-weight: bold;">
                            {c_info['delta_abs']:+d} ({c_info['delta_pct']:+.1f}%)
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # Comparação dos erros desse cliente específico
                errs_start = {e["erro"]: e["quantidade"] for e in get_client_errors(start_snap["id"], sel_cli_cmp)}
                errs_end = {e["erro"]: e["quantidade"] for e in get_client_errors(end_snap["id"], sel_cli_cmp)}
                all_err_keys = sorted(set(errs_start.keys()) | set(errs_end.keys()))

                cli_err_rows = []
                for ek in all_err_keys:
                    qs = errs_start.get(ek, 0)
                    qe = errs_end.get(ek, 0)
                    d = qe - qs
                    cli_err_rows.append(
                        {
                            "Erro": ek,
                            f"Qtd ({date_start})": qs,
                            f"Qtd ({date_end})": qe,
                            "Variação (Δ)": f"{d:+d}",
                        }
                    )
                st.dataframe(pd.DataFrame(cli_err_rows), use_container_width=True, hide_index=True)

        st.divider()

        # BLOCO 5: PRINCIPAIS ERROS COMPARATIVOS
        st.markdown("#### 5. ⚠️ Comparação de Tipos de Erro")
        if error_vars:
            df_evars = pd.DataFrame(
                [
                    {
                        "Erro": ev["erro"],
                        "Tipo": "🔍 Consulta" if ev["tipo"] == "consulta" else "👤 Usuário" if ev["tipo"] == "usuario" else "❓ Não Classificado",
                        f"Qtd ({date_start})": ev["qtd_start"],
                        f"Qtd ({date_end})": ev["qtd_end"],
                        "Variação (Δ)": f"{ev['delta_abs']:+d}",
                        "Variação (%)": f"{ev['delta_pct']:+.1f}%",
                    }
                    for ev in error_vars
                ]
            )
            st.dataframe(df_evars, use_container_width=True, hide_index=True)

        st.divider()

        # BLOCO 6: MAIORES AUMENTOS E REDUÇÕES
        st.markdown("#### 6. 🔺 Risers & Fallers (Maiores Variações)")
        col_r, col_f = st.columns(2)
        with col_r:
            st.markdown("##### 🔺 Maiores Aumentos (Atenção)")
            if risers:
                df_r = pd.DataFrame(
                    [
                        {
                            "Cliente": r["cliente"],
                            f"Em {date_start}": r["total_start"],
                            f"Em {date_end}": r["total_end"],
                            "Aumento": f"+{r['delta_abs']} ({r['delta_pct']:+.1f}%)",
                        }
                        for r in risers[:8]
                    ]
                )
                st.dataframe(df_r, use_container_width=True, hide_index=True)
            else:
                st.success("🎉 Nenhum cliente apresentou aumento de erros entre as datas!")

        with col_f:
            st.markdown("##### 🔽 Maiores Reduções (Melhorias)")
            if fallers:
                df_f = pd.DataFrame(
                    [
                        {
                            "Cliente": f["cliente"],
                            f"Em {date_start}": f["total_start"],
                            f"Em {date_end}": f["total_end"],
                            "Redução": f"{f['delta_abs']} ({f['delta_pct']:+.1f}%)",
                        }
                        for f in fallers[:8]
                    ]
                )
                st.dataframe(df_f, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum cliente com redução no período comparado.")

        st.divider()

        # BLOCO 7: RESUMO EXECUTIVO DA DAILY (COMPARATIVO)
        st.markdown("#### 7. 📋 Resumo Executivo da Daily (Comparativo)")
        cmp_ans = get_daily_answers_comparison(date_start, date_end)
        if cmp_ans and not cmp_ans.get("error"):
            tot_s = cmp_ans["start"]["total_erros"]
            tot_e = cmp_ans["end"]["total_erros"]
            d_abs = cmp_ans["metrics"]["total_erros"]["delta_abs"]
            d_pct = cmp_ans["metrics"]["total_erros"]["delta_pct"]
            cli_s = cmp_ans["start"]["clientes_afetados"]
            cli_e = cmp_ans["end"]["clientes_afetados"]
            top_c = cmp_ans.get("top_client")
            top_share = cmp_ans.get("top_client_share", 0.0)
            t_risers = cmp_ans.get("risers", [])
            t_fallers = cmp_ans.get("fallers", [])

            var_txt = (
                f"🔺 **Aumentou em {d_abs} erros ({d_pct:+.1f}%)**"
                if d_abs > 0
                else f"🔽 **Reduziu em {abs(d_abs)} erros ({d_pct:+.1f}%)**"
                if d_abs < 0
                else "⏸️ **Volume idêntico** entre as datas"
            )

            risers_txt = ", ".join([f"**{r['cliente']}** (+{r['delta_abs']})" for r in t_risers[:3]]) if t_risers else "Nenhum cliente com aumento."
            fallers_txt = ", ".join([f"**{f['cliente']}** ({f['delta_abs']})" for f in t_fallers[:3]]) if t_fallers else "Nenhuma redução expressiva."
            top_c_txt = f"**{top_c['cliente']}** com **{top_c['total_end']} erros** em {date_end} ({top_share:.1f}% do volume)" if top_c else "Nenhum"

            st.markdown(
                f"""
                <div style="background: rgba(17, 24, 39, 0.75); border: 1px solid rgba(139, 92, 246, 0.35); border-radius: 12px; padding: 20px; line-height: 1.8;">
                    <ol style="margin-left: -10px; color: #e2e8f0; font-size: 1.02rem;">
                        <li><b>Volume em {lbl_start}:</b> <code>{tot_s} erros</code></li>
                        <li><b>Volume em {lbl_end}:</b> <code>{tot_e} erros</code></li>
                        <li><b>Variação líquida:</b> {var_txt}</li>
                        <li><b>Dispersão de clientes:</b> <code>{cli_s} clientes</code> em {date_start} ➔ <code>{cli_e} clientes</code> em {date_end}</li>
                        <li><b>Cliente com maior concentração na data final:</b> {top_c_txt}</li>
                        <li><b>Clientes com maior aumento (Atenção):</b> {risers_txt}</li>
                        <li><b>Clientes com maior redução:</b> {fallers_txt}</li>
                    </ol>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # =========================================================================
    # MODO 3: PERÍODO (Intervalo De -> Até sem inventar dados vazios)
    # =========================================================================
    elif modo_analise == "Período":
        dates_asc = sorted(available_dates)
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            p_start = st.selectbox(
                "📅 **De:**",
                options=dates_asc,
                index=0,
                format_func=_format_date_option,
                key="period_start_sel",
            )
        with col_p2:
            p_end = st.selectbox(
                "📅 **Até:**",
                options=dates_asc,
                index=len(dates_asc) - 1,
                format_func=_format_date_option,
                key="period_end_sel",
            )

        period_data = get_period_data(p_start, p_end)
        if not period_data or period_data.get("dias_com_snapshot", 0) == 0:
            st.warning("Nenhum dado encontrado para o período selecionado.")
            return

        snapshots_period = period_data["snapshots"]
        dias_com_snap = period_data["dias_com_snapshot"]
        tot_periodo = period_data["total_erros_periodo"]
        cons_periodo = period_data["erros_consulta_periodo"]
        usr_periodo = period_data["erros_usuario_periodo"]
        clientes_unicos = period_data["total_clientes_unicos"]
        media_diaria = period_data["media_diaria_erros"]
        dia_pico = period_data["dia_pico"]
        client_ranking_period = period_data["client_ranking"]
        top_errors_period = period_data["top_errors"]

        st.markdown(
            f"""
            <div style="background: rgba(30, 41, 59, 0.5); border: 1px solid rgba(139, 92, 246, 0.25); border-radius: 8px; padding: 12px 18px; margin-bottom: 18px; font-size: 0.95rem; color: #cbd5e1;">
                🗓️ Analisando período de <b>{_format_date_option(period_data['date_start'])}</b> até <b>{_format_date_option(period_data['date_end'])}</b>. 
                Total de <b>{dias_com_snap} dia(s)</b> com planilhas processadas.
            </div>
            """,
            unsafe_allow_html=True,
        )

        # BLOCO 1: PANORAMA DO PERÍODO
        st.markdown("#### 1. 📌 Panorama do Período")
        m1, m2, m3, m4, m5 = st.columns(5)
        with m1:
            st.metric("Total Acumulado", tot_periodo, help="Soma de todos os erros em todos os snapshots do período.")
        with m2:
            st.metric("Média Diária", f"{media_diaria:.1f}", help="Média de erros por dia com snapshot registrado.")
        with m3:
            st.metric("Clientes Únicos", clientes_unicos, help="Quantidade de clientes distintos afetados em todo o período (contados 1 única vez).")
        with m4:
            st.metric("Erros Consulta", cons_periodo, help="Volume acumulado de erros de consulta no período.")
        with m5:
            st.metric("Erros Usuário", usr_periodo, help="Volume acumulado de erros de usuário no período.")

        st.divider()

        # BLOCO 2: EVOLUÇÃO DIÁRIA NO PERÍODO (Sem inventar dias vazios)
        st.markdown("#### 2. 📈 Evolução Diária no Período")
        st.caption("Gráfico com os pontos reais registrados (sem interpolação de dias sem dados).")
        if snapshots_period:
            df_psnaps = pd.DataFrame(snapshots_period)
            df_pchart = pd.DataFrame(
                {
                    "Data": df_psnaps["data"].apply(lambda d: datetime.strptime(d, "%Y-%m-%d").strftime("%d/%m")),
                    "Total de Erros": df_psnaps["total_erros"],
                    "Erros Consulta": df_psnaps["erros_consulta"],
                    "Erros Usuário": df_psnaps["erros_usuario"],
                }
            ).set_index("Data")
            st.line_chart(df_pchart, height=280)

        st.divider()

        # BLOCO 3: CLIENTES MAIS IMPACTADOS NO PERÍODO
        st.markdown("#### 3. 👥 Clientes com Maior Volume Acumulado")
        st.caption("Consolidação dos clientes no período selecionado.")
        if client_ranking_period:
            df_pcli = pd.DataFrame(
                [
                    {
                        "Cliente": c["cliente"],
                        "Total no Período": c["total_erros"],
                        "Erros Consulta": c["erros_consulta"],
                        "Erros Usuário": c["erros_usuario"],
                        "Dias com Erro": f"{c['dias_com_erro']} / {dias_com_snap}",
                        "Representatividade": f"{(c['total_erros'] / tot_periodo * 100.0):.1f}%" if tot_periodo > 0 else "0.0%",
                    }
                    for c in client_ranking_period
                ]
            )
            st.dataframe(df_pcli, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum cliente registrado no período.")

        st.divider()

        # BLOCO 4: DETALHAMENTO DO CLIENTE NO PERÍODO
        st.markdown("#### 4. 🔍 Detalhamento do Cliente no Período")
        if client_ranking_period:
            p_cli_names = [c["cliente"] for c in client_ranking_period]
            sel_p_cli = st.selectbox("Selecione um cliente para detalhar no período:", options=p_cli_names, key="period_client_select")
            p_cli_info = next((c for c in client_ranking_period if c["cliente"] == sel_p_cli), None)

            if p_cli_info:
                pdc1, pdc2, pdc3, pdc4 = st.columns(4)
                with pdc1:
                    st.metric("Total no Período", p_cli_info["total_erros"])
                with pdc2:
                    st.metric("Erros Consulta", p_cli_info["erros_consulta"])
                with pdc3:
                    st.metric("Erros Usuário", p_cli_info["erros_usuario"])
                with pdc4:
                    st.metric("Dias Presente", f"{p_cli_info['dias_com_erro']} dias")

                cli_p_evo = get_client_evolution(sel_p_cli, date_start=period_data["date_start"], date_end=period_data["date_end"])
                if cli_p_evo and len(cli_p_evo) > 1:
                    st.markdown("##### 📈 Evolução Diária deste Cliente no Período")
                    df_cp_evo = pd.DataFrame(cli_p_evo)
                    df_cp_chart = pd.DataFrame(
                        {
                            "Data": df_cp_evo["data"].apply(lambda d: datetime.strptime(d, "%Y-%m-%d").strftime("%d/%m")),
                            "Total": df_cp_evo["total_erros"],
                        }
                    ).set_index("Data")
                    st.line_chart(df_cp_chart, height=200)

        st.divider()

        # BLOCO 5: PRINCIPAIS ERROS NO PERÍODO
        st.markdown("#### 5. ⚠️ Principais Erros no Período")
        if top_errors_period:
            df_ptop = pd.DataFrame(
                [
                    {
                        "Erro": te["erro"],
                        "Tipo": "🔍 Consulta" if te["tipo"] == "consulta" else "👤 Usuário" if te["tipo"] == "usuario" else "❓ Não Classificado",
                        "Volume Acumulado": te["total_quantidade"],
                        "Dias Presente": f"{te['dias_presente']} dia(s)",
                        "Clientes Afetados": te["clientes_afetados"],
                    }
                    for te in top_errors_period
                ]
            )
            st.dataframe(df_ptop, use_container_width=True, hide_index=True)

        st.divider()

        # BLOCO 7: RESUMO EXECUTIVO DO PERÍODO
        st.markdown("#### 7. 📋 Resumo Executivo do Período")
        p_ans = get_daily_answers_period(period_data["date_start"], period_data["date_end"])
        if p_ans and not p_ans.get("error"):
            dia_pico_str = (
                f"{_format_date_option(dia_pico['data'])} ({dia_pico['total_erros']} erros)"
                if dia_pico
                else "N/A"
            )
            top_cli_p = p_ans.get("top_client")
            top_cli_p_txt = f"**{top_cli_p['cliente']}** com **{top_cli_p['total_erros']} erros** ({p_ans.get('top_client_share', 0.0):.1f}% do total)" if top_cli_p else "Nenhum"
            top_errs_p_txt = ", ".join([f"**{e['erro']}** ({e['total_quantidade']}x em {e['dias_presente']} dias)" for e in p_ans.get("top_errors", [])[:3]]) or "Nenhum"

            st.markdown(
                f"""
                <div style="background: rgba(17, 24, 39, 0.75); border: 1px solid rgba(139, 92, 246, 0.35); border-radius: 12px; padding: 20px; line-height: 1.8;">
                    <ol style="margin-left: -10px; color: #e2e8f0; font-size: 1.02rem;">
                        <li><b>Período analisado:</b> de {_format_date_option(p_ans['date_start'])} até {_format_date_option(p_ans['date_end'])} (<code>{dias_com_snap} dias com dados</code>)</li>
                        <li><b>Volume total acumulado:</b> <code>{tot_periodo} erros</code></li>
                        <li><b>Média diária nos dias ativos:</b> <code>{media_diaria:.1f} erros/dia</code></li>
                        <li><b>Total de clientes distintos afetados no período:</b> <code>{clientes_unicos} clientes únicos</code></li>
                        <li><b>Dia com maior volume (Pico):</b> {dia_pico_str}</li>
                        <li><b>Cliente com maior volume acumulado:</b> {top_cli_p_txt}</li>
                        <li><b>Erros com maior recorrência no período:</b> {top_errs_p_txt}</li>
                    </ol>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # =========================================================================
    # SEÇÃO DE GERENCIAMENTO DO HISTÓRICO (EXCLUSÃO SEGURA)
    # =========================================================================
    st.divider()
    with st.expander("⚙️ Gerenciar Histórico do Daily", expanded=False):
        st.markdown("##### 🗑️ Excluir Histórico de uma Data")
        st.caption(
            "Permite remover com segurança os registros de um dia incorreto ou obsoleto. "
            "Esta operação apaga exclusivamente o snapshot e as tabelas diárias daquela data, "
            "preservando 100% dos contatos e do histórico de mensagens operacionais."
        )
        col_del_sel, col_del_btn = st.columns([2, 1.5])
        with col_del_sel:
            date_to_delete = st.selectbox(
                "Selecione a data para excluir:",
                options=available_dates,
                format_func=_format_date_option,
                key="daily_manage_date_to_delete",
            )

        del_confirm_state_key = f"confirming_delete_{date_to_delete}"
        if not st.session_state.get(del_confirm_state_key, False):
            with col_del_btn:
                st.write("")
                st.write("")
                if st.button("🗑️ Excluir esta data", key=f"btn_init_del_{date_to_delete}"):
                    st.session_state[del_confirm_state_key] = True
                    st.rerun()
        else:
            d_fmt = _format_date_option(date_to_delete)
            st.warning(f"⚠️ **Atenção:** Deseja realmente excluir permanentemente o histórico de **{d_fmt}**?")
            col_c_del, col_ok_del = st.columns([1, 1.5])
            with col_c_del:
                if st.button("❌ Cancelar", key=f"btn_cancel_del_{date_to_delete}"):
                    st.session_state[del_confirm_state_key] = False
                    st.rerun()
            with col_ok_del:
                if st.button("🗑️ Confirmar Exclusão", type="primary", key=f"btn_confirm_del_{date_to_delete}"):
                    ok_del, msg_del = delete_snapshot_by_date(date_to_delete)
                    st.session_state[del_confirm_state_key] = False
                    if ok_del:
                        st.success(f"✅ {msg_del}")
                    else:
                        st.error(f"❌ {msg_del}")
                    st.rerun()

