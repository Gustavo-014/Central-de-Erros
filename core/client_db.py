import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.db import get_connection, init_db


def _format_date_br(iso_date: Optional[str]) -> str:
    """Converte 'YYYY-MM-DD' para 'DD/MM/YYYY'."""
    if not iso_date:
        return "—"
    try:
        dt = datetime.strptime(iso_date, "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return iso_date


def save_client_consultas(
    consultas: List[Dict[str, Any]],
    force_replace: bool = True,
) -> Tuple[int, int]:
    """
    Persiste consultas e erros por cliente no SQLite de forma idempotente e atômica.
    
    Regras de duplicidade:
    - Chave única da consulta: (cliente, data_consulta).
    - Se a consulta para o cliente e data já existir:
        - Se file_hash for idêntico e force_replace=False: mantém sem duplicar.
        - Se force_replace=True ou file_hash diferente: atualiza a consulta e substitui os erros.
    - Se a consulta não existir: insere nova consulta e seus respectivos erros.
    
    Retorna: (total_consultas_salvas, total_erros_salvos)
    """
    if not consultas:
        return 0, 0

    init_db()
    consultas_salvas = 0
    erros_salvos = 0

    with get_connection() as conn:
        cursor = conn.cursor()

        for c in consultas:
            cliente = str(c.get("cliente", "")).strip()
            data_consulta = str(c.get("data_consulta", "")).strip()
            total_erros = int(c.get("total_erros", 0))
            tipos_erros = int(c.get("tipos_erros", 0))
            file_hash = str(c.get("file_hash", "")).strip()
            erros = c.get("erros", [])

            if not cliente or not data_consulta:
                continue

            # Verificar se já existe consulta para esse cliente nessa data
            cursor.execute(
                "SELECT id, file_hash FROM client_history_consultas WHERE cliente = ? AND data_consulta = ?",
                (cliente, data_consulta),
            )
            existing = cursor.fetchone()

            if existing:
                consulta_id = existing["id"]
                existing_hash = existing["file_hash"]

                # Se o hash for idêntico e não for substituição forçada, pula
                if existing_hash == file_hash and not force_replace:
                    continue

                # Atualiza a consulta
                cursor.execute(
                    """
                    UPDATE client_history_consultas
                    SET total_erros = ?, tipos_erros = ?, file_hash = ?, created_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (total_erros, tipos_erros, file_hash, consulta_id),
                )

                # Remove detalhamento anterior de erros dessa consulta
                cursor.execute("DELETE FROM client_history_erros WHERE consulta_id = ?", (consulta_id,))
            else:
                cursor.execute(
                    """
                    INSERT INTO client_history_consultas (
                        cliente, data_consulta, total_erros, tipos_erros, file_hash, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (cliente, data_consulta, total_erros, tipos_erros, file_hash),
                )
                consulta_id = cursor.lastrowid

            consultas_salvas += 1

            # Inserir detalhamento dos erros
            for err in erros:
                erro_nome = str(err.get("erro", "")).strip()
                tipo = str(err.get("tipo", "nao_classificado")).strip()
                quantidade = int(err.get("quantidade", 1))
                indicadores_list = err.get("indicadores", [])
                indicadores_json = json.dumps(indicadores_list, ensure_ascii=False) if indicadores_list else None

                if not erro_nome:
                    continue

                cursor.execute(
                    """
                    INSERT INTO client_history_erros (
                        consulta_id, cliente, data_consulta, erro, tipo, quantidade, indicadores
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        consulta_id,
                        cliente,
                        data_consulta,
                        erro_nome,
                        tipo,
                        quantidade,
                        indicadores_json,
                    ),
                )
                erros_salvos += 1

        conn.commit()

    return consultas_salvas, erros_salvos


def get_all_history_clients() -> List[str]:
    """Retorna lista alfabética de todos os clientes que possuem histórico de consultas."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT cliente 
            FROM client_history_consultas 
            ORDER BY cliente COLLATE NOCASE ASC
            """
        )
        return [row["cliente"] for row in cursor.fetchall()]


def get_client_summary(cliente: str) -> Dict[str, Any]:
    """
    Retorna o resumo consolidado do cliente:
    - total_consultas
    - primeira_consulta (DD/MM/YYYY e ISO)
    - ultima_consulta (DD/MM/YYYY e ISO)
    - total_erros
    """
    init_db()
    cliente_clean = cliente.strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                COUNT(*) as total_consultas,
                MIN(data_consulta) as primeira_consulta,
                MAX(data_consulta) as ultima_consulta,
                COALESCE(SUM(total_erros), 0) as total_erros
            FROM client_history_consultas
            WHERE cliente = ?
            """,
            (cliente_clean,),
        )
        row = cursor.fetchone()
        if not row or row["total_consultas"] == 0:
            return {
                "cliente": cliente_clean,
                "total_consultas": 0,
                "primeira_consulta": "—",
                "primeira_consulta_iso": None,
                "ultima_consulta": "—",
                "ultima_consulta_iso": None,
                "total_erros": 0,
            }

        p_iso = row["primeira_consulta"]
        u_iso = row["ultima_consulta"]

        return {
            "cliente": cliente_clean,
            "total_consultas": row["total_consultas"],
            "primeira_consulta": _format_date_br(p_iso),
            "primeira_consulta_iso": p_iso,
            "ultima_consulta": _format_date_br(u_iso),
            "ultima_consulta_iso": u_iso,
            "total_erros": row["total_erros"],
        }


def get_client_consultas_history(cliente: str) -> List[Dict[str, Any]]:
    """
    Retorna a lista de consultas do cliente em ordem cronológica decrescente:
    - data_consulta (ISO e formatada)
    - total_erros
    - tipos_erros
    - erros_resumo (string com descrição amigável, ex: '5 tipos')
    - top_erros_nomes (nomes dos erros mais frequentes naquela consulta)
    """
    init_db()
    cliente_clean = cliente.strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, data_consulta, total_erros, tipos_erros
            FROM client_history_consultas
            WHERE cliente = ?
            ORDER BY data_consulta DESC
            """,
            (cliente_clean,),
        )
        consultas_rows = cursor.fetchall()

        history = []
        for c in consultas_rows:
            consulta_id = c["id"]
            d_iso = c["data_consulta"]

            cursor.execute(
                """
                SELECT erro, quantidade
                FROM client_history_erros
                WHERE consulta_id = ?
                ORDER BY quantidade DESC
                """,
                (consulta_id,),
            )
            erros_rows = cursor.fetchall()
            num_tipos = len(erros_rows)
            top_erros = [f"{e['erro']} ({e['quantidade']})" for e in erros_rows[:3]]

            resumo_texto = f"{num_tipos} tipo{'s' if num_tipos != 1 else ''}"
            if top_erros:
                resumo_texto += f": {', '.join(top_erros)}"

            history.append({
                "consulta_id": consulta_id,
                "data_consulta_iso": d_iso,
                "data_consulta": _format_date_br(d_iso),
                "total_erros": c["total_erros"],
                "tipos_erros": num_tipos,
                "erros_resumo": f"{num_tipos} tipo{'s' if num_tipos != 1 else ''}",
                "erros_detalhe_texto": resumo_texto,
            })

        return history


def get_client_error_ranking(cliente: str) -> List[Dict[str, Any]]:
    """
    Retorna o ranking consolidado de erros do cliente ordenado por quantidade decrescente:
    - erro
    - tipo
    - total_ocorrencias
    - percentual
    """
    init_db()
    cliente_clean = cliente.strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                erro, 
                tipo, 
                SUM(quantidade) as total_ocorrencias,
                COUNT(DISTINCT data_consulta) as consultas_afetadas
            FROM client_history_erros
            WHERE cliente = ?
            GROUP BY erro
            ORDER BY total_ocorrencias DESC, erro ASC
            """,
            (cliente_clean,),
        )
        rows = cursor.fetchall()
        tot_geral = sum(r["total_ocorrencias"] for r in rows)

        ranking = []
        for r in rows:
            qtd = r["total_ocorrencias"]
            pct = (qtd / tot_geral * 100.0) if tot_geral > 0 else 0.0
            ranking.append({
                "erro": r["erro"],
                "tipo": r["tipo"],
                "total_ocorrencias": qtd,
                "consultas_afetadas": r["consultas_afetadas"],
                "percentual": pct,
            })

        return ranking


def get_client_evolution(cliente: str) -> List[Dict[str, Any]]:
    """
    Retorna a evolução temporal de erros do cliente em ordem cronológica crescente (para gráficos):
    - data_consulta_iso
    - data_consulta (DD/MM/YYYY)
    - total_erros
    - erros_consulta (se disponível)
    - erros_usuario (se disponível)
    """
    init_db()
    cliente_clean = cliente.strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                c.data_consulta,
                c.total_erros,
                COALESCE(SUM(CASE WHEN e.tipo = 'consulta' THEN e.quantidade ELSE 0 END), 0) as erros_consulta,
                COALESCE(SUM(CASE WHEN e.tipo = 'usuario' THEN e.quantidade ELSE 0 END), 0) as erros_usuario,
                COALESCE(SUM(CASE WHEN e.tipo = 'nao_classificado' THEN e.quantidade ELSE 0 END), 0) as erros_nao_classificados
            FROM client_history_consultas c
            LEFT JOIN client_history_erros e ON c.id = e.consulta_id
            WHERE c.cliente = ?
            GROUP BY c.id, c.data_consulta, c.total_erros
            ORDER BY c.data_consulta ASC
            """,
            (cliente_clean,),
        )
        rows = cursor.fetchall()

        return [
            {
                "data_consulta_iso": r["data_consulta"],
                "data_consulta": _format_date_br(r["data_consulta"]),
                "total_erros": r["total_erros"],
                "erros_consulta": r["erros_consulta"],
                "erros_usuario": r["erros_usuario"],
                "erros_nao_classificados": r["erros_nao_classificados"],
            }
            for r in rows
        ]


def get_client_available_dates(cliente: str) -> List[str]:
    """Retorna as datas de consulta de um cliente em ordem decrescente (ISO)."""
    init_db()
    cliente_clean = cliente.strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT data_consulta 
            FROM client_history_consultas 
            WHERE cliente = ? 
            ORDER BY data_consulta DESC
            """,
            (cliente_clean,),
        )
        return [r["data_consulta"] for r in cursor.fetchall()]


def get_client_consulta_details(cliente: str, data_consulta: str) -> List[Dict[str, Any]]:
    """
    Retorna o detalhamento completo dos erros de uma consulta específica:
    - erro
    - tipo
    - quantidade
    - indicadores (lista de strings, ex: placas, cnpjs, etc.)
    """
    init_db()
    cliente_clean = cliente.strip()
    data_clean = data_consulta.strip()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT erro, tipo, quantidade, indicadores
            FROM client_history_erros
            WHERE cliente = ? AND data_consulta = ?
            ORDER BY quantidade DESC, erro ASC
            """,
            (cliente_clean, data_clean),
        )
        rows = cursor.fetchall()

        details = []
        for r in rows:
            indicadores_raw = r["indicadores"]
            indicadores_list = []
            if indicadores_raw:
                try:
                    indicadores_list = json.loads(indicadores_raw)
                except Exception:
                    indicadores_list = [indicadores_raw]

            details.append({
                "erro": r["erro"],
                "tipo": r["tipo"],
                "quantidade": r["quantidade"],
                "indicadores": indicadores_list,
            })

        return details
