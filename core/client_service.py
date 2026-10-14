import hashlib
import json
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from core.client_db import save_client_consultas
from core.error_classifier import classify_error
from core.error_normalizer import normalize_error
from core.extractor import extract_occurrence
from core.template_loader import load_templates
from core.utils import normalize_text as _base_normalize


def _normalize_text(value: str) -> str:
    """Normaliza texto para comparação tolerante em relação a formatação."""
    return _base_normalize(value).casefold()


def parse_data_consulta(val: Any) -> Optional[str]:
    """
    Extrai e normaliza a data da coluna 'Data Consulta' para o formato ISO 'YYYY-MM-DD'.
    
    Regra estrita:
    - Utiliza exatamente a data existente na planilha.
    - Não infere, substitui ou inventa datas a partir da data de upload.
    - Retorna None caso o valor seja nulo ou inválido.
    """
    if val is None or pd.isna(val):
        return None

    # Se já for Timestamp ou objeto com strftime (date, datetime)
    if hasattr(val, "strftime"):
        try:
            return val.strftime("%Y-%m-%d")
        except Exception:
            pass

    raw_str = str(val).strip()
    if not raw_str or raw_str.lower() in {"nan", "nat", "none", "null", ""}:
        return None

    # Se contiver horário (ex: "10/07/2026 14:30:00" ou "2026-07-10T00:00:00"), pegar a parte da data
    part_date = raw_str.split()[0].split("T")[0].strip()

    # Padrão DD/MM/YYYY ou DD-MM-YYYY
    m_br = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", part_date)
    if m_br:
        d, m, y = int(m_br.group(1)), int(m_br.group(2)), int(m_br.group(3))
        if 1 <= m <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{m:02d}-{d:02d}"

    # Padrão YYYY-MM-DD ou YYYY/MM/DD
    m_iso = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", part_date)
    if m_iso:
        y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        if 1 <= m <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{m:02d}-{d:02d}"

    # Tentar via pandas pd.to_datetime com dayfirst=True
    try:
        dt = pd.to_datetime(val, dayfirst=True)
        if pd.notna(dt):
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass

    return None


def find_data_consulta_column(dataframe: pd.DataFrame) -> Optional[str]:
    """
    Identifica o nome exato da coluna 'Data Consulta' no DataFrame.
    Prioriza correspondência exata e é tolerante a variações sutis de maiúsculas/espaços.
    """
    if dataframe.empty:
        return None

    columns = list(dataframe.columns)

    # 1. Correspondência exata
    if "Data Consulta" in columns:
        return "Data Consulta"

    # 2. Correspondência normalizada sem acentos/casing
    for col in columns:
        col_norm = _normalize_text(str(col)).strip()
        if col_norm in {"data consulta", "data da consulta", "dataconsulta"}:
            return col

    # 3. Correspondência parcial (contém 'data' e 'consulta')
    for col in columns:
        col_norm = _normalize_text(str(col))
        if "data" in col_norm and "consulta" in col_norm:
            return col

    # 4. Fallback: Coluna A (índice 0) se contiver valores válidos de data
    if len(columns) > 0:
        first_col = columns[0]
        # Testar se as primeiras linhas não nulas da coluna 0 são datas válidas
        sample_vals = dataframe[first_col].dropna().head(5)
        if not sample_vals.empty:
            valid_dates = [parse_data_consulta(v) for v in sample_vals]
            if any(valid_dates) and (len([v for v in valid_dates if v is not None]) >= len(sample_vals) * 0.5):
                return first_col

    return None


def _format_indicator(occurrence: Dict[str, Any], template: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    Formata o identificador do erro (placa, cnpj, renavam) de acordo com o template ou os dados presentes.
    """
    if template and "campos_exibicao" in template:
        fields = template["campos_exibicao"]
        values = []
        for field in fields:
            val = occurrence.get(field)
            if val not in [None, ""]:
                values.append(str(val).strip())
        if values:
            return " - ".join(values)

    # Fallback se não houver template: priorizar placa, renavam, cnpj
    parts = []
    if occurrence.get("placa"):
        parts.append(str(occurrence["placa"]).strip())
    if occurrence.get("renavam"):
        parts.append(f"Renavam: {occurrence['renavam']}")
    if occurrence.get("cnpj"):
        parts.append(str(occurrence["cnpj"]).strip())

    return " - ".join(parts) if parts else None


def extract_client_history_from_dataframe(
    dataframe: pd.DataFrame,
    file_hash: str = "",
) -> List[Dict[str, Any]]:
    """
    Processa o DataFrame e agrupa as ocorrências por (cliente, data_consulta).
    
    Aproveita toda a lógica existente de normalização (normalize_error),
    classificação (classify_error) e templates (templates.json).
    
    Evita registros duplicados quando o mesmo cliente aparece múltiplas vezes na mesma execução.
    """
    if dataframe.empty:
        return []

    data_col = find_data_consulta_column(dataframe)
    if not data_col:
        return []

    templates = load_templates()
    normalized_templates = {
        _normalize_text(key): value for key, value in templates.items()
    }

    # Estrutura agrupada: (cliente, data_consulta) -> erro_nome -> {'tipo': str, 'indicadores': set/list, 'qtd': int}
    grouped: Dict[Tuple[str, str], Dict[str, Dict[str, Any]]] = {}

    for row in dataframe.to_dict("records"):
        raw_data = row.get(data_col)
        data_consulta = parse_data_consulta(raw_data)
        if not data_consulta:
            # Sem data oficial, não infere data
            continue

        occ = extract_occurrence(row)
        cliente = occ.get("cliente")
        erro_orig = occ.get("erro_original")

        if not cliente or not erro_orig:
            continue

        erro_norm = normalize_error(erro_orig)
        if not erro_norm:
            continue

        # Validar se há ao menos um indicador na linha (mesma regra de process_dataframe)
        if not any(v for v in occ.values() if v not in [None, ""] and v != cliente and v != erro_orig):
            continue

        key = (cliente, data_consulta)
        if key not in grouped:
            grouped[key] = {}

        if erro_norm not in grouped[key]:
            tipo, _ = classify_error(erro_norm, row)
            template = templates.get(erro_norm) or normalized_templates.get(_normalize_text(erro_norm))
            grouped[key][erro_norm] = {
                "tipo": tipo,
                "template": template,
                "indicadores": [],
                "indicadores_set": set(),
                "quantidade": 0,
            }

        grouped[key][erro_norm]["quantidade"] += 1

        # Formatar e coletar indicador individual
        ind_str = _format_indicator(occ, grouped[key][erro_norm]["template"])
        if ind_str and ind_str not in grouped[key][erro_norm]["indicadores_set"]:
            grouped[key][erro_norm]["indicadores_set"].add(ind_str)
            grouped[key][erro_norm]["indicadores"].append(ind_str)

    # Converter para lista de consultas estruturadas
    consultas: List[Dict[str, Any]] = []
    for (cliente, data_consulta), erros_dict in sorted(grouped.items()):
        total_erros = sum(err_info["quantidade"] for err_info in erros_dict.values())
        tipos_erros = len(erros_dict)

        erros_list = []
        for erro_nome, err_info in sorted(erros_dict.items()):
            erros_list.append({
                "erro": erro_nome,
                "tipo": err_info["tipo"],
                "quantidade": err_info["quantidade"],
                "indicadores": err_info["indicadores"],
            })

        consultas.append({
            "cliente": cliente,
            "data_consulta": data_consulta,
            "total_erros": total_erros,
            "tipos_erros": tipos_erros,
            "file_hash": file_hash,
            "erros": erros_list,
        })

    return consultas


def record_client_history(
    dataframe: pd.DataFrame,
    file_hash: str = "",
    force_replace: bool = True,
) -> Tuple[bool, str, int]:
    """
    Processa a planilha e salva atomicamente o histórico de consultas por cliente no banco SQLite.
    
    Retorna: (sucesso, mensagem, total_consultas_processadas)
    """
    if dataframe.empty:
        return False, "Planilha vazia.", 0

    data_col = find_data_consulta_column(dataframe)
    if not data_col:
        return False, "Coluna 'Data Consulta' não encontrada na planilha.", 0

    consultas = extract_client_history_from_dataframe(dataframe, file_hash=file_hash)
    if not consultas:
        return False, "Nenhuma ocorrência válida com 'Data Consulta' encontrada.", 0

    c_salvas, e_salvos = save_client_consultas(consultas, force_replace=force_replace)
    msg = f"Histórico de clientes atualizado: {c_salvas} consulta(s) e {e_salvos} erro(s) registrados."
    return True, msg, c_salvas
