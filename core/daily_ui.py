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
        return f"+{delta_abs} (+{delta_pct:.1f}%)"
    if delta_abs < 0:
        return f"{delta_abs} ({delta_pct:.1f}%)"
    return "0 (0.0%)"


def render_acompanhamento_tab() -> None:
    """Renderiza a interface completa da aba Acompanhamento com 3 modos de análise focada no Total de Erros."""
    available_dates = get_available_dates()

    if not available_dates:
        st.html(
            """
            <div class="empty-state-card">
                <div class="empty-state-icon">
                    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-6l-2 3h-4l-2-3H2"></path><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"></path></svg>
                </div>
                <div class="empty-state-title">Nenhum snapshot diário registrado ainda</div>
                <div class="empty-state-desc">
                    Para iniciar o histórico de Acompanhamento Daily, acesse a aba <b>Operacional (Envio)</b> e importe uma planilha de erros.
                    O sistema registrará automaticamente o snapshot com a data de incidência no banco SQLite.
                </div>
            </div>
            """
        )
        return

    # -------------------------------------------------------------------------
    # CONTROLES SUPERIORES: MODO DE ANÁLISE E FILTROS DE DATAS
    # -------------------------------------------------------------------------
    st.markdown("### Acompanhamento Daily")
    st.caption("Visão consolidada de indicadores, evolução diária e análise comparativa de erros.")

    col_mode, col_info = st.columns([2.5, 2.5])
    with col_mode:
        modo_analise = st.radio(
            "Modo de Análise:",
            options=["Um dia", "Comparar datas", "Período"],
            index=0,
            horizontal=True,
            key="daily_mode_radio",
        )

    with col_info:
        total_snaps = len(available_dates)
        mais_antigo = _format_date_option(available_dates[-1])
        mais_recente = _format_date_option(available_dates[0])
        st.html(
            f"""
            <div style="background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 10px 14px; font-size: 0.85rem; color: #94a3b8;">
                <div><b>Histórico Disponível:</b> <span style="color: #f1f5f9;">{total_snaps} dia{'s' if total_snaps > 1 else ''} registrado{'s' if total_snaps > 1 else ''}</span></div>
                <div style="margin-top: 3px;"><b>Período:</b> <code>{mais_antigo}</code> até <code>{mais_recente}</code></div>
            </div>
            """
        )

    st.write("")

    # =========================================================================
    # MODO 1: UM DIA (Sem comparação automática com dia anterior)
    # =========================================================================
    if modo_analise == "Um dia":
        col_f1, col_f2 = st.columns([1.5, 3.5])
        with col_f1:
            selected_date = st.selectbox(
                "Data Analisada:",
                options=available_dates,
                index=0,
                format_func=_format_date_option,
                key="daily_single_date",
            )

        snap = get_snapshot_by_date(selected_date)
        if not snap:
            st.warning("Não foi possível carregar os dados para a data selecionada.", icon=":material/warning:")
            return

        with col_f2:
            file_orig = snap.get("file_name") or "Planilha importada"
            created_at = snap.get("created_at") or ""
            st.html(
                f"""
                <div style="padding-top: 26px; font-size: 0.88rem; color: #94a3b8;">
                    Origem: <code>{file_orig}</code> &nbsp;|&nbsp; Processado em: <code>{created_at}</code>
                </div>
                """
            )

        snapshot_id = snap["id"]
        client_ranking = get_client_ranking(snapshot_id)
        top_errors = get_top_errors(snapshot_id)

        st.write("")

        # BLOCO 1: PANORAMA GERAL
        st.markdown("#### 1. Panorama Geral")
        st.caption("Visão dos indicadores da data selecionada.")
        p1, p2, p3 = st.columns(3)
        with p1:
            st.metric("Total de Erros", snap["total_erros"], help="Volume total de ocorrências de erros na planilha desta data.")
        with p2:
            st.metric("Clientes Afetados", snap["clientes_afetados"], help="Total de clientes distintos que tiveram pelo menos 1 erro nesta data.")
        with p3:
            media_por_cli = (snap["total_erros"] / snap["clientes_afetados"]) if snap["clientes_afetados"] > 0 else 0.0
            st.metric("Média de Erros / Cliente", f"{media_por_cli:.1f}", help="Média de erros por cliente afetado nesta data.")

        st.divider()

        # BLOCO 2: EVOLUÇÃO DIÁRIA
        st.markdown("#### 2. Evolução Diária do Total de Erros")
        history_records = get_snapshots_evolution()
        if history_records:
            df_hist = pd.DataFrame(history_records)
            df_chart = pd.DataFrame(
                {
                    "Data": df_hist["data"].apply(lambda d: datetime.strptime(d, "%Y-%m-%d").strftime("%d/%m")),
                    "Total de Erros": df_hist["total_erros"],
                }
            ).set_index("Data")
            st.line_chart(df_chart, height=280)
        else:
            st.info("Histórico insuficiente para gerar gráfico.", icon=":material/info:")

        st.divider()

        # BLOCO 3: CONCENTRAÇÃO POR CLIENTE
        st.markdown("#### 3. Concentração por Cliente")
        st.caption(f"Ranking dos clientes com maior quantidade de erros na data {_format_date_option(selected_date)}.")
        if client_ranking:
            df_cli = pd.DataFrame(
                [
                    {
                        "Cliente": c["cliente"],
                        "Total de Erros": c["total_erros"],
                        "Representatividade": f"{(c['total_erros'] / snap['total_erros'] * 100.0):.1f}%" if snap['total_erros'] > 0 else "0.0%",
                    }
                    for c in client_ranking
                ]
            )
            st.dataframe(df_cli, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum cliente com erros nesta data.", icon=":material/info:")

        st.divider()

        # BLOCO 4: DETALHAMENTO DO CLIENTE
        st.markdown("#### 4. Detalhamento do Cliente")
        if client_ranking:
            client_names = [c["cliente"] for c in client_ranking]
            selected_client = st.selectbox("Selecione um cliente para inspecionar:", options=client_names, key="single_client_select")
            cli_data = next((c for c in client_ranking if c["cliente"] == selected_client), None)

            if cli_data:
                dc1, dc2 = st.columns(2)
                with dc1:
                    st.metric("Total do Cliente", cli_data["total_erros"])
                with dc2:
                    share_cli = (cli_data["total_erros"] / snap["total_erros"] * 100.0) if snap["total_erros"] > 0 else 0.0
                    st.metric("Participação no Total do Dia", f"{share_cli:.1f}%")

                col_cevo, col_ctab = st.columns([1.2, 1.8])
                with col_cevo:
                    st.markdown("##### Histórico deste Cliente")
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
                        st.caption("Apenas 1 registro diário disponível para este cliente.")

                with col_ctab:
                    st.markdown("##### Erros Deste Cliente")
                    cli_errs = get_client_errors(snapshot_id, selected_client)
                    if cli_errs:
                        df_cerrs = pd.DataFrame(
                            [
                                {
                                    "Erro": e["erro"],
                                    "Ocorrências": e["quantidade"],
                                }
                                for e in cli_errs
                            ]
                        )
                        st.dataframe(df_cerrs, use_container_width=True, hide_index=True)
                    else:
                        st.info("Nenhum detalhe de erro encontrado.", icon=":material/info:")

        st.divider()

        # BLOCO 5: PRINCIPAIS ERROS
        st.markdown("#### 5. Principais Erros no Dia")
        if top_errors:
            df_top = pd.DataFrame(
                [
                    {
                        "Erro": te["erro"],
                        "Total Ocorrências": te["total_quantidade"],
                        "Clientes Afetados": te["clientes_afetados"],
                    }
                    for te in top_errors
                ]
            )
            st.dataframe(df_top, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum erro registrado.", icon=":material/info:")

        st.divider()

        # BLOCO 6: RESUMO EXECUTIVO
        st.markdown("#### 6. Resumo Executivo da Daily")
        answers = get_daily_answers_single(selected_date)
        if answers:
            tot = answers["total_erros"]
            afet = answers["clientes_afetados"]
            top_c = answers.get("top_client")
            top_share = answers.get("top_client_share", 0.0)
            t_errs = answers.get("top_errors", [])
            t_rec = answers.get("recurrent_errors", [])

            top_c_txt = f"<b>{top_c['cliente']}</b> com <b>{top_c['total_erros']} erros</b> ({top_share:.1f}% do total do dia)" if top_c else "Nenhum"
            top_e_txt = ", ".join([f"<b>{e['erro']}</b> ({e['total_quantidade']}x)" for e in t_errs[:3]]) if t_errs else "Nenhum"
            rec_txt = ", ".join([f"<b>{e['erro']}</b> ({e['dias_presente']} dias)" for e in t_rec[:3]]) if t_rec else "Sem problemas recorrentes em múltiplos dias."
            med_txt = f"{(tot / afet):.1f} erros/cliente" if afet > 0 else "0 erros/cliente"

            st.html(
                f"""
                <div class="executive-summary-card">
                    <div class="summary-header">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                        <span>Resumo Executivo da Daily</span>
                    </div>
                    <ol class="summary-list">
                        <li><b>Volume total na data:</b> <code>{tot} erros</code></li>
                        <li><b>Clientes impactados:</b> <code>{afet} clientes distintos</code></li>
                        <li><b>Média de concentração:</b> <code>{med_txt}</code></li>
                        <li><b>Maior cliente do dia:</b> {top_c_txt}</li>
                        <li><b>Principais problemas no dia:</b> {top_e_txt}</li>
                        <li><b>Problemas recorrentes no histórico:</b> {rec_txt}</li>
                    </ol>
                </div>
                """
            )

    # =========================================================================
    # MODO 2: COMPARAR DATAS (date_start < date_end com cálculo date_end - date_start)
    # =========================================================================
    elif modo_analise == "Comparar datas":
        if len(available_dates) < 2:
            st.info("São necessárias ao menos 2 datas com snapshots registradas para realizar comparações. Importe planilhas de outros dias para habilitar.", icon=":material/info:")
            return

        dates_asc = sorted(available_dates)
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            date_start_input = st.selectbox(
                "Data Inicial (Base):",
                options=dates_asc,
                index=0,
                format_func=_format_date_option,
                key="cmp_date_start",
            )
        with col_c2:
            date_end_input = st.selectbox(
                "Data Final (Comparada):",
                options=dates_asc,
                index=len(dates_asc) - 1,
                format_func=_format_date_option,
                key="cmp_date_end",
            )

        # Validação obrigatória: datas devem ser diferentes
        if date_start_input == date_end_input:
            st.warning("A Data Inicial e a Data Final devem ser diferentes para comparação. Selecione duas datas distintas.", icon=":material/warning:")
            return

        # Ajustar para garantir date_start < date_end
        if date_start_input > date_end_input:
            date_start, date_end = date_end_input, date_start_input
            st.info(f"As datas foram organizadas cronologicamente para a comparação: **{_format_date_option(date_start)}** → **{_format_date_option(date_end)}**.", icon=":material/info:")
        else:
            date_start, date_end = date_start_input, date_end_input

        comp = get_comparison_data(date_start, date_end)
        if not comp or comp.get("error"):
            st.error(comp.get("error", "Erro ao comparar datas."), icon=":material/error:")
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

        st.html(
            f"""
            <div class="info-banner">
                <div class="info-banner-icon">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>
                </div>
                <div>
                    Comparando variação: <b>{lbl_start}</b> (Base) &nbsp;➔&nbsp; <b>{lbl_end}</b> (Atual). 
                    Fórmula: <code>Δ = {lbl_end} - {lbl_start}</code>
                </div>
            </div>
            """
        )

        # BLOCO 1: PANORAMA COMPARATIVO
        st.markdown("#### 1. Panorama Comparativo")
        cp1, cp2 = st.columns(2)

        with cp1:
            tot_m = metrics["total_erros"]
            delta_str = _format_delta_badge(tot_m["delta_abs"], tot_m["delta_pct"])
            st.html(
                f"""
                <div class="metric-card" style="text-align: left; padding: 16px;">
                    <div style="font-size: 0.78rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600;">Total de Erros</div>
                    <div style="font-size: 1.25rem; color: #f1f5f9; margin-top: 6px;">
                        <b>Inicial:</b> {tot_m['start']} &nbsp;|&nbsp; <b>Final:</b> {tot_m['end']}
                    </div>
                    <div style="font-size: 1.1rem; margin-top: 8px; font-weight: bold; color: {'#ef4444' if tot_m['delta_abs'] > 0 else '#10b981' if tot_m['delta_abs'] < 0 else '#cbd5e1'};">
                        {delta_str}
                    </div>
                </div>
                """
            )

        with cp2:
            cli_m = metrics["clientes_afetados"]
            delta_str = _format_delta_badge(cli_m["delta_abs"], cli_m["delta_pct"])
            st.html(
                f"""
                <div class="metric-card" style="text-align: left; padding: 16px;">
                    <div style="font-size: 0.78rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600;">Clientes Afetados</div>
                    <div style="font-size: 1.25rem; color: #f1f5f9; margin-top: 6px;">
                        <b>Inicial:</b> {cli_m['start']} &nbsp;|&nbsp; <b>Final:</b> {cli_m['end']}
                    </div>
                    <div style="font-size: 1.1rem; margin-top: 8px; font-weight: bold; color: {'#ef4444' if cli_m['delta_abs'] > 0 else '#10b981' if cli_m['delta_abs'] < 0 else '#cbd5e1'};">
                        {delta_str}
                    </div>
                </div>
                """
            )

        st.divider()

        # BLOCO 2: GRÁFICO COMPARATIVO
        st.markdown("#### 2. Comparativo Gráfico")
        df_cmp_bars = pd.DataFrame(
            {
                "Indicador": ["Total de Erros", "Clientes Afetados"],
                f"Data Inicial ({date_start})": [tot_m["start"], cli_m["start"]],
                f"Data Final ({date_end})": [tot_m["end"], cli_m["end"]],
            }
        ).set_index("Indicador")
        st.bar_chart(df_cmp_bars, height=280)

        st.divider()

        # BLOCO 3: CONCENTRAÇÃO POR CLIENTE (COMPARATIVO)
        st.markdown("#### 3. Comparação por Cliente")
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
                        "Situação": "Novo" if c["is_new"] else "Resolvido" if c["is_resolved"] else "Aumento (+)" if c["delta_abs"] > 0 else "Redução (-)" if c["delta_abs"] < 0 else "Estável",
                    }
                    for c in client_vars
                ]
            )
            st.dataframe(df_cvars, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum cliente registrado nas datas selecionadas.", icon=":material/info:")

        st.divider()

        # BLOCO 4: DETALHAMENTO DO CLIENTE (COMPARATIVO)
        st.markdown("#### 4. Detalhamento do Cliente na Comparação")
        if client_vars:
            cli_names = [c["cliente"] for c in client_vars]
            sel_cli_cmp = st.selectbox("Selecione um cliente para comparar:", options=cli_names, key="cmp_client_select")
            c_info = next((c for c in client_vars if c["cliente"] == sel_cli_cmp), None)

            if c_info:
                st.html(
                    f"""
                    <div style="background: rgba(30, 41, 59, 0.6); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 12px 18px; margin-bottom: 12px;">
                        <b>Cliente:</b> <code>{sel_cli_cmp}</code><br>
                        <b>{date_start}:</b> {c_info['total_start']} erros &nbsp;|&nbsp; 
                        <b>{date_end}:</b> {c_info['total_end']} erros &nbsp;|&nbsp; 
                        <b>Variação:</b> <span style="color: {'#ef4444' if c_info['delta_abs'] > 0 else '#10b981' if c_info['delta_abs'] < 0 else '#cbd5e1'}; font-weight: bold;">
                            {c_info['delta_abs']:+d} ({c_info['delta_pct']:+.1f}%)
                        </span>
                    </div>
                    """
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
        st.markdown("#### 5. Comparação dos Principais Erros")
        if error_vars:
            df_evars = pd.DataFrame(
                [
                    {
                        "Erro": ev["erro"],
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
        st.markdown("#### 6. Maiores Variações (Risers & Fallers)")
        col_r, col_f = st.columns(2)
        with col_r:
            st.markdown("##### Maiores Aumentos (Atenção)")
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
                st.success("Nenhum cliente apresentou aumento de erros entre as datas!")

        with col_f:
            st.markdown("##### Maiores Reduções (Melhorias)")
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
                st.info("Nenhum cliente com redução no período comparado.", icon=":material/info:")

        st.divider()

        # BLOCO 7: RESUMO EXECUTIVO DA DAILY (COMPARATIVO)
        st.markdown("#### 7. Resumo Executivo da Daily (Comparativo)")
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
                f"**Aumentou em {d_abs} erros ({d_pct:+.1f}%)**"
                if d_abs > 0
                else f"**Reduziu em {abs(d_abs)} erros ({d_pct:+.1f}%)**"
                if d_abs < 0
                else "**Volume estável** entre as datas"
            )

            risers_txt = ", ".join([f"<b>{r['cliente']}</b> (+{r['delta_abs']})" for r in t_risers[:3]]) if t_risers else "Nenhum cliente com aumento."
            fallers_txt = ", ".join([f"<b>{f['cliente']}</b> ({f['delta_abs']})" for f in t_fallers[:3]]) if t_fallers else "Nenhuma redução expressiva."
            top_c_txt = f"<b>{top_c['cliente']}</b> com <b>{top_c['total_end']} erros</b> em {date_end} ({top_share:.1f}% do volume)" if top_c else "Nenhum"

            st.html(
                f"""
                <div class="executive-summary-card">
                    <div class="summary-header">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                        <span>Resumo Executivo da Daily (Comparativo)</span>
                    </div>
                    <ol class="summary-list">
                        <li><b>Volume em {lbl_start}:</b> <code>{tot_s} erros</code></li>
                        <li><b>Volume em {lbl_end}:</b> <code>{tot_e} erros</code></li>
                        <li><b>Variação líquida:</b> {var_txt}</li>
                        <li><b>Dispersão de clientes:</b> <code>{cli_s} clientes</code> em {date_start} ➔ <code>{cli_e} clientes</code> em {date_end}</li>
                        <li><b>Cliente com maior concentração na data final:</b> {top_c_txt}</li>
                        <li><b>Clientes com maior aumento (Atenção):</b> {risers_txt}</li>
                        <li><b>Clientes com maior redução:</b> {fallers_txt}</li>
                    </ol>
                </div>
                """
            )

    # =========================================================================
    # MODO 3: PERÍODO (Intervalo De -> Até sem inventar dados vazios)
    # =========================================================================
    elif modo_analise == "Período":
        dates_asc = sorted(available_dates)
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            p_start = st.selectbox(
                "De:",
                options=dates_asc,
                index=0,
                format_func=_format_date_option,
                key="period_start_sel",
            )
        with col_p2:
            p_end = st.selectbox(
                "Até:",
                options=dates_asc,
                index=len(dates_asc) - 1,
                format_func=_format_date_option,
                key="period_end_sel",
            )

        period_data = get_period_data(p_start, p_end)
        if not period_data or period_data.get("dias_com_snapshot", 0) == 0:
            st.warning("Nenhum dado encontrado para o período selecionado.", icon=":material/warning:")
            return

        snapshots_period = period_data["snapshots"]
        dias_com_snap = period_data["dias_com_snapshot"]
        tot_periodo = period_data["total_erros_periodo"]
        clientes_unicos = period_data["total_clientes_unicos"]
        media_diaria = period_data["media_diaria_erros"]
        dia_pico = period_data["dia_pico"]
        client_ranking_period = period_data["client_ranking"]
        top_errors_period = period_data["top_errors"]

        st.html(
            f"""
            <div class="info-banner">
                <div class="info-banner-icon">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
                </div>
                <div>
                    Analisando período de <b>{_format_date_option(period_data['date_start'])}</b> até <b>{_format_date_option(period_data['date_end'])}</b>. 
                    Total de <b>{dias_com_snap} dia(s)</b> com planilhas processadas.
                </div>
            </div>
            """
        )

        # BLOCO 1: PANORAMA DO PERÍODO
        st.markdown("#### 1. Panorama do Período")
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Total Acumulado de Erros", tot_periodo, help="Soma de todos os erros em todos os snapshots do período.")
        with m2:
            st.metric("Média Diária", f"{media_diaria:.1f}", help="Média de erros por dia com snapshot registrado.")
        with m3:
            st.metric("Clientes Únicos Afetados", clientes_unicos, help="Quantidade de clientes distintos afetados em todo o período (contados 1 única vez).")

        st.divider()

        # BLOCO 2: EVOLUÇÃO DIÁRIA NO PERÍODO (Sem inventar dias vazios)
        st.markdown("#### 2. Evolução Diária no Período")
        st.caption("Gráfico com o Total de Erros nos dias reais registrados (sem interpolação de dias vazios).")
        if snapshots_period:
            df_psnaps = pd.DataFrame(snapshots_period)
            df_pchart = pd.DataFrame(
                {
                    "Data": df_psnaps["data"].apply(lambda d: datetime.strptime(d, "%Y-%m-%d").strftime("%d/%m")),
                    "Total de Erros": df_psnaps["total_erros"],
                }
            ).set_index("Data")
            st.line_chart(df_pchart, height=280)

        st.divider()

        # BLOCO 3: CLIENTES MAIS IMPACTADOS NO PERÍODO
        st.markdown("#### 3. Clientes com Maior Volume Acumulado")
        st.caption("Consolidação dos clientes no período selecionado.")
        if client_ranking_period:
            df_pcli = pd.DataFrame(
                [
                    {
                        "Cliente": c["cliente"],
                        "Total no Período": c["total_erros"],
                        "Dias com Erro": f"{c['dias_com_erro']} / {dias_com_snap}",
                        "Representatividade": f"{(c['total_erros'] / tot_periodo * 100.0):.1f}%" if tot_periodo > 0 else "0.0%",
                    }
                    for c in client_ranking_period
                ]
            )
            st.dataframe(df_pcli, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum cliente registrado no período.", icon=":material/info:")

        st.divider()

        # BLOCO 4: DETALHAMENTO DO CLIENTE NO PERÍODO
        st.markdown("#### 4. Detalhamento do Cliente no Período")
        if client_ranking_period:
            p_cli_names = [c["cliente"] for c in client_ranking_period]
            sel_p_cli = st.selectbox("Selecione um cliente para detalhar no período:", options=p_cli_names, key="period_client_select")
            p_cli_info = next((c for c in client_ranking_period if c["cliente"] == sel_p_cli), None)

            if p_cli_info:
                pdc1, pdc2, pdc3 = st.columns(3)
                with pdc1:
                    st.metric("Total no Período", p_cli_info["total_erros"])
                with pdc2:
                    st.metric("Dias Presente", f"{p_cli_info['dias_com_erro']} dias")
                with pdc3:
                    med_cli = (p_cli_info["total_erros"] / p_cli_info["dias_com_erro"]) if p_cli_info["dias_com_erro"] > 0 else 0.0
                    st.metric("Média por Dia Ativo", f"{med_cli:.1f}")

                cli_p_evo = get_client_evolution(sel_p_cli, date_start=period_data["date_start"], date_end=period_data["date_end"])
                if cli_p_evo and len(cli_p_evo) > 1:
                    st.markdown("##### Evolução Diária deste Cliente no Período")
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
        st.markdown("#### 5. Principais Erros no Período")
        if top_errors_period:
            df_ptop = pd.DataFrame(
                [
                    {
                        "Erro": te["erro"],
                        "Volume Acumulado": te["total_quantidade"],
                        "Dias Presente": f"{te['dias_presente']} dia(s)",
                        "Clientes Afetados": te["clientes_afetados"],
                    }
                    for te in top_errors_period
                ]
            )
            st.dataframe(df_ptop, use_container_width=True, hide_index=True)

        st.divider()

        # BLOCO 6: RESUMO EXECUTIVO DO PERÍODO
        st.markdown("#### 6. Resumo Executivo do Período")
        p_ans = get_daily_answers_period(period_data["date_start"], period_data["date_end"])
        if p_ans and not p_ans.get("error"):
            dia_pico_str = (
                f"{_format_date_option(dia_pico['data'])} ({dia_pico['total_erros']} erros)"
                if dia_pico
                else "N/A"
            )
            top_cli_p = p_ans.get("top_client")
            top_cli_p_txt = f"<b>{top_cli_p['cliente']}</b> com <b>{top_cli_p['total_erros']} erros</b> ({p_ans.get('top_client_share', 0.0):.1f}% do total)" if top_cli_p else "Nenhum"
            top_errs_p_txt = ", ".join([f"<b>{e['erro']}</b> ({e['total_quantidade']}x em {e['dias_presente']} dias)" for e in p_ans.get("top_errors", [])[:3]]) or "Nenhum"

            st.html(
                f"""
                <div class="executive-summary-card">
                    <div class="summary-header">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                        <span>Resumo Executivo do Período</span>
                    </div>
                    <ol class="summary-list">
                        <li><b>Período analisado:</b> de {_format_date_option(p_ans['date_start'])} até {_format_date_option(p_ans['date_end'])} (<code>{dias_com_snap} dias com dados</code>)</li>
                        <li><b>Volume total acumulado:</b> <code>{tot_periodo} erros</code></li>
                        <li><b>Média diária nos dias ativos:</b> <code>{media_diaria:.1f} erros/dia</code></li>
                        <li><b>Total de clientes distintos afetados no período:</b> <code>{clientes_unicos} clientes únicos</code></li>
                        <li><b>Dia com maior volume (Pico):</b> {dia_pico_str}</li>
                        <li><b>Cliente com maior volume acumulado:</b> {top_cli_p_txt}</li>
                        <li><b>Erros com maior recorrência no período:</b> {top_errs_p_txt}</li>
                    </ol>
                </div>
                """
            )

    # =========================================================================
    # SEÇÃO DE GERENCIAMENTO DO HISTÓRICO (EXCLUSÃO SEGURA)
    # =========================================================================
    st.divider()
    with st.expander("Gerenciar Histórico do Daily", expanded=False, icon=":material/settings:"):
        st.markdown("##### Excluir Histórico de uma Data")
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
                if st.button("Excluir esta data", icon=":material/delete:", key=f"btn_init_del_{date_to_delete}"):
                    st.session_state[del_confirm_state_key] = True
                    st.rerun()
        else:
            d_fmt = _format_date_option(date_to_delete)
            st.warning(f"Deseja realmente excluir permanentemente o histórico de **{d_fmt}**?", icon=":material/warning:")
            col_c_del, col_ok_del = st.columns([1, 1.5])
            with col_c_del:
                if st.button("Cancelar", icon=":material/close:", key=f"btn_cancel_del_{date_to_delete}"):
                    st.session_state[del_confirm_state_key] = False
                    st.rerun()
            with col_ok_del:
                if st.button("Confirmar Exclusão", icon=":material/delete_forever:", type="primary", key=f"btn_confirm_del_{date_to_delete}"):
                    ok_del, msg_del = delete_snapshot_by_date(date_to_delete)
                    st.session_state[del_confirm_state_key] = False
                    if ok_del:
                        st.success(msg_del, icon=":material/check_circle:")
                    else:
                        st.error(msg_del, icon=":material/error:")
                    st.rerun()
