import hashlib
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from core.daily_db import (
    get_comparison_data,
    get_period_data,
    get_recurrent_errors,
    get_snapshot_by_date,
    get_top_errors,
    save_or_update_snapshot,
)
from core.error_classifier import classify_error
from core.error_normalizer import normalize_error
from core.extractor import extract_occurrence


def extract_date_from_filename(filename: str, default_year: Optional[int] = None) -> Optional[str]:
    """
    Extrai a data de incidência contida no nome do arquivo (ex: erros-28/08, erros-28-08, erros_29_08).
    Retorna no formato ISO 'YYYY-MM-DD' ou None se não encontrar.
    """
    if not filename:
        return None

    # 1. YYYY-MM-DD
    m1 = re.search(r"(?:^|[^\d])(\d{4})[-_./](\d{1,2})[-_./](\d{1,2})(?:[^\d]|$)", filename)
    if m1:
        y, m, d = int(m1.group(1)), int(m1.group(2)), int(m1.group(3))
        if 1 <= m <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{m:02d}-{d:02d}"

    # 2. DD-MM-YYYY
    m2 = re.search(r"(?:^|[^\d])(\d{1,2})[-_./](\d{1,2})[-_./](\d{4})(?:[^\d]|$)", filename)
    if m2:
        d, m, y = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
        if 1 <= m <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{m:02d}-{d:02d}"

    # 3. DD-MM (ex: erros-28/08, erros-28-08, erros_29_08, 28.08)
    m3 = re.search(r"(?:^|[^\d])(\d{1,2})[-_./](\d{1,2})(?:[^\d]|$)", filename)
    if m3:
        d, m = int(m3.group(1)), int(m3.group(2))
        if 1 <= m <= 12 and 1 <= d <= 31:
            y = default_year or datetime.now().year
            return f"{y:04d}-{m:02d}-{d:02d}"

    return None


def compute_file_hash(file_bytes: bytes) -> str:
    """Calcula o hash SHA-256 do conteúdo bruto do arquivo."""
    return hashlib.sha256(file_bytes).hexdigest()


def record_daily_snapshot(
    dados: Dict[str, Dict[str, List[Dict[str, str]]]],
    dataframe: Optional[pd.DataFrame] = None,
    filename: str = "",
    file_bytes: Optional[bytes] = None,
    target_date: Optional[str] = None,
    force_replace: bool = False,
) -> Tuple[bool, str]:
    """
    Consolida as métricas a partir dos dados processados e persiste o snapshot no SQLite.
    
    A data padrão é a data atual (YYYY-MM-DD), a menos que especificada.
    O file_hash é a chave técnica de verificação de duplicidade.
    Garante a correta amarração da linha bruta por par (cliente, erro) para classificação por coluna.
    """
    if not dados:
        return False, "Nenhum dado processado para gerar o snapshot."

    # Data de referência
    date_str = target_date or datetime.now().strftime("%Y-%m-%d")

    # Hash do arquivo
    if file_bytes:
        f_hash = compute_file_hash(file_bytes)
    else:
        repr_str = f"{date_str}_{filename}_{sorted(dados.keys())}"
        f_hash = hashlib.sha256(repr_str.encode("utf-8")).hexdigest()

    client_metrics_map: Dict[str, Dict[str, Any]] = {}
    error_details: List[Dict[str, Any]] = []

    # Mapear linhas brutas indexadas por (cliente, erro_normalizado) e por erro_normalizado
    raw_rows_by_client_error: Dict[Tuple[str, str], Dict[str, Any]] = {}
    raw_rows_by_error: Dict[str, Dict[str, Any]] = {}
    if dataframe is not None and not dataframe.empty:
        for row in dataframe.to_dict("records"):
            occ = extract_occurrence(row)
            cli = occ.get("cliente")
            err_orig = occ.get("erro_original")
            if err_orig:
                err_norm = normalize_error(err_orig)
                if err_norm:
                    if cli and (cli, err_norm) not in raw_rows_by_client_error:
                        raw_rows_by_client_error[(cli, err_norm)] = row
                    if err_norm not in raw_rows_by_error:
                        raw_rows_by_error[err_norm] = row

    for cliente, erros in dados.items():
        if cliente not in client_metrics_map:
            client_metrics_map[cliente] = {
                "cliente": cliente,
                "total_erros": 0,
                "erros_consulta": 0,
                "erros_usuario": 0,
                "erros_nao_classificados": 0,
            }

        for erro_nome, ocorrencias in erros.items():
            qtd = len(ocorrencias)
            if qtd <= 0:
                continue

            # Buscar a linha bruta exata correspondente ao par (cliente, erro)
            raw_sample = raw_rows_by_client_error.get((cliente, erro_nome)) or raw_rows_by_error.get(erro_nome)

            # Classificar o erro respeitando a hierarquia:
            # 1. Coluna da linha correspondente
            # 2. templates.json
            # 3. error_types.json
            # 4. Palavras-chave
            # 5. nao_classificado
            tipo, _ = classify_error(erro_nome, raw_sample)

            # Acumular no cliente
            client_metrics_map[cliente]["total_erros"] += qtd
            if tipo == "consulta":
                client_metrics_map[cliente]["erros_consulta"] += qtd
            elif tipo == "usuario":
                client_metrics_map[cliente]["erros_usuario"] += qtd
            else:
                client_metrics_map[cliente]["erros_nao_classificados"] += qtd

            # Adicionar detalhe do erro por cliente
            error_details.append(
                {
                    "cliente": cliente,
                    "erro": erro_nome,
                    "tipo": tipo,
                    "quantidade": qtd,
                }
            )

    client_metrics = list(client_metrics_map.values())
    total_erros = sum(c["total_erros"] for c in client_metrics)
    erros_consulta = sum(c["erros_consulta"] for c in client_metrics)
    erros_usuario = sum(c["erros_usuario"] for c in client_metrics)
    erros_nao_classificados = sum(c["erros_nao_classificados"] for c in client_metrics)
    clientes_afetados = len([c for c in client_metrics if c["total_erros"] > 0])

    success, msg, _ = save_or_update_snapshot(
        data=date_str,
        file_hash=f_hash,
        file_name=filename or "planilha_processada.xlsx",
        total_erros=total_erros,
        erros_consulta=erros_consulta,
        erros_usuario=erros_usuario,
        erros_nao_classificados=erros_nao_classificados,
        clientes_afetados=clientes_afetados,
        client_metrics=client_metrics,
        error_details=error_details,
        force_replace=force_replace,
    )

    return success, msg


def get_daily_answers_single(selected_date: str) -> Dict[str, Any]:
    """
    Compila as respostas para a Daily focando exclusivamente em um único dia selecionado.
    Sem comparação implícita ou automática com dia anterior.
    """
    snap = get_snapshot_by_date(selected_date)
    if not snap:
        return {}

    snapshot_id = snap["id"]
    from core.daily_db import get_client_ranking
    clients = get_client_ranking(snapshot_id)
    top_errors = get_top_errors(snapshot_id)
    recurrent_errors = get_recurrent_errors(min_days=2)

    total_erros = snap["total_erros"]
    top_client = clients[0] if clients else None
    top_client_share = (
        (top_client["total_erros"] / total_erros * 100.0)
        if top_client and total_erros > 0
        else 0.0
    )

    return {
        "mode": "single",
        "data": selected_date,
        "total_erros": total_erros,
        "erros_consulta": snap["erros_consulta"],
        "erros_usuario": snap["erros_usuario"],
        "erros_nao_classificados": snap["erros_nao_classificados"],
        "clientes_afetados": snap["clientes_afetados"],
        "top_client": top_client,
        "top_client_share": top_client_share,
        "top_errors": top_errors[:5],
        "recurrent_errors": recurrent_errors[:5],
    }


def get_daily_answers_comparison(date_start: str, date_end: str) -> Dict[str, Any]:
    """
    Compila as respostas para a Daily comparando EXPLICITAMENTE duas datas escolhidas pelo usuário.
    Regra: date_start < date_end, delta = date_end - date_start.
    """
    comp = get_comparison_data(date_start, date_end)
    if not comp or comp.get("error"):
        return {"error": comp.get("error", "Não foi possível comparar as datas selecionadas.")}

    start = comp["start"]
    end = comp["end"]
    metrics = comp.get("metrics", {})
    client_vars = comp.get("client_variations", [])
    risers = comp.get("risers", [])
    fallers = comp.get("fallers", [])
    top_errors = get_top_errors(end["id"])

    total_end = end["total_erros"]
    top_client = client_vars[0] if client_vars else None
    top_client_share = (
        (top_client["total_end"] / total_end * 100.0)
        if top_client and total_end > 0
        else 0.0
    )

    return {
        "mode": "comparison",
        "date_start": comp["date_start"],
        "date_end": comp["date_end"],
        "start": start,
        "end": end,
        "metrics": metrics,
        "top_client": top_client,
        "top_client_share": top_client_share,
        "risers": risers[:5],
        "fallers": fallers[:5],
        "top_errors": top_errors[:5],
    }


def get_daily_answers_period(date_start: str, date_end: str) -> Dict[str, Any]:
    """
    Compila as respostas para a Daily resumindo um período selecionado pelo usuário.
    """
    period_info = get_period_data(date_start, date_end)
    if not period_info or period_info.get("dias_com_snapshot", 0) == 0:
        return {"error": "Nenhum snapshot encontrado para o período selecionado."}

    client_ranking = period_info.get("client_ranking", [])
    top_client = client_ranking[0] if client_ranking else None
    tot_periodo = period_info["total_erros_periodo"]
    top_client_share = (
        (top_client["total_erros"] / tot_periodo * 100.0)
        if top_client and tot_periodo > 0
        else 0.0
    )

    return {
        "mode": "period",
        "date_start": period_info["date_start"],
        "date_end": period_info["date_end"],
        "dias_com_snapshot": period_info["dias_com_snapshot"],
        "total_erros_periodo": tot_periodo,
        "erros_consulta_periodo": period_info["erros_consulta_periodo"],
        "erros_usuario_periodo": period_info["erros_usuario_periodo"],
        "erros_nao_classificados_periodo": period_info["erros_nao_classificados_periodo"],
        "total_clientes_unicos": period_info["total_clientes_unicos"],
        "media_diaria_erros": period_info["media_diaria_erros"],
        "dia_pico": period_info["dia_pico"],
        "top_client": top_client,
        "top_client_share": top_client_share,
        "top_errors": period_info.get("top_errors", [])[:5],
    }


def get_daily_answers(selected_date: str) -> Dict[str, Any]:
    """Compatibilidade retroativa: chama get_daily_answers_single."""
    return get_daily_answers_single(selected_date)
