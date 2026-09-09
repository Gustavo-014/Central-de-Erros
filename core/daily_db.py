import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from core.db import get_connection, init_db


def save_or_update_snapshot(
    data: str,
    file_hash: str,
    file_name: str,
    total_erros: int,
    erros_consulta: int,
    erros_usuario: int,
    erros_nao_classificados: int,
    clientes_afetados: int,
    client_metrics: List[Dict[str, Any]],
    error_details: List[Dict[str, Any]],
    force_replace: bool = False,
) -> Tuple[bool, str, Optional[int]]:
    """
    Salva ou atualiza atomicamente um snapshot diário com garantia de integridade.
    
    Regras de duplicidade:
    - Se a data já existe e o hash do arquivo é idêntico: não grava duplicado.
    - Se a data já existe e force_replace=False: retorna aviso de que já existe e requer confirmação.
    - Se a data já existe e force_replace=True: substitui atomicamente o snapshot daquela data.
    - Se a data não existe: insere novo snapshot.
    """
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Verificar existência prévia para a mesma data
        cursor.execute("SELECT id, file_hash, file_name, created_at FROM daily_snapshots WHERE data = ?", (data,))
        existing = cursor.fetchone()
        
        if existing:
            existing_id = existing["id"]
            existing_hash = existing["file_hash"]
            
            # Se o conteúdo do arquivo é idêntico, ignorar para evitar duplicidade
            if existing_hash == file_hash:
                return True, "Snapshot com o mesmo conteúdo já registrado para esta data.", existing_id
            
            # Se já existe e não foi solicitada confirmação explícita de substituição, bloquear
            if not force_replace:
                return False, "EXISTS", existing_id

            # Se o usuário confirmou explicitamente a substituição, excluir dados anteriores
            cursor.execute("DELETE FROM daily_snapshots WHERE id = ?", (existing_id,))
        
        # Inserir o snapshot
        cursor.execute(
            """
            INSERT INTO daily_snapshots (
                data, file_name, file_hash, total_erros, erros_consulta, 
                erros_usuario, erros_nao_classificados, clientes_afetados, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                data,
                file_name,
                file_hash,
                total_erros,
                erros_consulta,
                erros_usuario,
                erros_nao_classificados,
                clientes_afetados,
            ),
        )
        snapshot_id = cursor.lastrowid
        
        # Inserir métricas dos clientes (com UNIQUE(snapshot_id, cliente))
        for cm in client_metrics:
            cursor.execute(
                """
                INSERT INTO daily_clientes (
                    snapshot_id, cliente, total_erros, erros_consulta, 
                    erros_usuario, erros_nao_classificados
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    cm["cliente"],
                    cm["total_erros"],
                    cm["erros_consulta"],
                    cm["erros_usuario"],
                    cm.get("erros_nao_classificados", 0),
                ),
            )
            
        # Inserir detalhamento dos erros (com UNIQUE(snapshot_id, cliente, erro, tipo))
        for ed in error_details:
            cursor.execute(
                """
                INSERT INTO daily_erros (
                    snapshot_id, cliente, erro, tipo, quantidade
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    ed["cliente"],
                    ed["erro"],
                    ed["tipo"],
                    ed["quantidade"],
                ),
            )
            
        conn.commit()
        return True, "Snapshot salvo com sucesso!", snapshot_id


def get_available_dates() -> List[str]:
    """Retorna lista de datas disponíveis com snapshots em ordem cronológica decrescente."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM daily_snapshots ORDER BY data DESC")
        return [row["data"] for row in cursor.fetchall()]


def get_snapshot_by_date(date_str: str) -> Optional[Dict[str, Any]]:
    """Retorna os dados consolidados do snapshot de uma data específica."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM daily_snapshots WHERE data = ?", (date_str,))
        row = cursor.fetchone()
        return dict(row) if row else None


def delete_snapshot_by_date(date_str: str) -> Tuple[bool, str]:
    """
    Exclui o snapshot de uma data específica e todas as suas dependências em cascata (daily_clientes e daily_erros).
    Garante que client_contacts e sent_history não sejam afetados.
    """
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM daily_snapshots WHERE data = ?", (date_str,))
        row = cursor.fetchone()
        if not row:
            return False, f"Nenhum snapshot encontrado para a data {date_str}."

        snapshot_id = row["id"]
        cursor.execute("DELETE FROM daily_snapshots WHERE id = ?", (snapshot_id,))
        conn.commit()
        return True, f"Histórico do dia {date_str} excluído com sucesso."


def get_previous_snapshot(date_str: str) -> Optional[Dict[str, Any]]:
    """Localiza o snapshot imediatamente anterior à data fornecida (utilitário opcional)."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM daily_snapshots WHERE data < ? ORDER BY data DESC LIMIT 1",
            (date_str,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_snapshots_evolution(
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Retorna a série histórica de snapshots em ordem cronológica (sem inventar dias vazios).
    Pode ser filtrada por intervalo [date_start, date_end] ou por limite de registros.
    """
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        if date_start and date_end:
            d_s, d_e = (date_start, date_end) if date_start <= date_end else (date_end, date_start)
            cursor.execute(
                "SELECT * FROM daily_snapshots WHERE data >= ? AND data <= ? ORDER BY data ASC",
                (d_s, d_e),
            )
            return [dict(row) for row in cursor.fetchall()]

        if limit and limit > 0:
            query = """
                SELECT * FROM (
                    SELECT * FROM daily_snapshots ORDER BY data DESC LIMIT ?
                ) ORDER BY data ASC
            """
            cursor.execute(query, (limit,))
            return [dict(row) for row in cursor.fetchall()]

        cursor.execute("SELECT * FROM daily_snapshots ORDER BY data ASC")
        return [dict(row) for row in cursor.fetchall()]


def get_client_ranking(snapshot_id: int) -> List[Dict[str, Any]]:
    """Retorna o ranking de clientes no snapshot ordenado pelo total de erros decrescente."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT cliente, total_erros, erros_consulta, erros_usuario, erros_nao_classificados
            FROM daily_clientes
            WHERE snapshot_id = ?
            ORDER BY total_erros DESC, cliente ASC
            """,
            (snapshot_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_client_evolution(
    client_name: str,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retorna a evolução histórica de um cliente específico, opcionalmente limitada a um período."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        if date_start and date_end:
            d_s, d_e = (date_start, date_end) if date_start <= date_end else (date_end, date_start)
            cursor.execute(
                """
                SELECT s.data, c.total_erros, c.erros_consulta, c.erros_usuario, c.erros_nao_classificados
                FROM daily_clientes c
                JOIN daily_snapshots s ON c.snapshot_id = s.id
                WHERE c.cliente = ? AND s.data >= ? AND s.data <= ?
                ORDER BY s.data ASC
                """,
                (client_name, d_s, d_e),
            )
        else:
            cursor.execute(
                """
                SELECT s.data, c.total_erros, c.erros_consulta, c.erros_usuario, c.erros_nao_classificados
                FROM daily_clientes c
                JOIN daily_snapshots s ON c.snapshot_id = s.id
                WHERE c.cliente = ?
                ORDER BY s.data ASC
                """,
                (client_name,),
            )
        return [dict(row) for row in cursor.fetchall()]


def get_client_errors(snapshot_id: int, client_name: str) -> List[Dict[str, Any]]:
    """Retorna a lista de erros de um cliente específico em determinado snapshot."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT erro, tipo, quantidade
            FROM daily_erros
            WHERE snapshot_id = ? AND cliente = ?
            ORDER BY quantidade DESC, erro ASC
            """,
            (snapshot_id, client_name),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_top_errors(snapshot_id: int) -> List[Dict[str, Any]]:
    """Retorna o ranking dos principais erros do snapshot agrupados pelo nome normalizado."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                erro, 
                tipo, 
                SUM(quantidade) AS total_quantidade, 
                COUNT(DISTINCT cliente) AS clientes_afetados 
            FROM daily_erros 
            WHERE snapshot_id = ? 
            GROUP BY erro, tipo 
            ORDER BY total_quantidade DESC, erro ASC
            """,
            (snapshot_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_recurrent_errors(min_days: int = 2) -> List[Dict[str, Any]]:
    """Retorna os erros que foram recorrentes ao longo de múltiplos dias."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                e.erro, 
                e.tipo, 
                COUNT(DISTINCT s.data) AS dias_presente, 
                SUM(e.quantidade) AS volume_acumulado 
            FROM daily_erros e 
            JOIN daily_snapshots s ON e.snapshot_id = s.id 
            GROUP BY e.erro, e.tipo 
            HAVING COUNT(DISTINCT s.data) >= ? 
            ORDER BY dias_presente DESC, volume_acumulado DESC
            """,
            (min_days,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_comparison_data(date_start: str, date_end: str) -> Dict[str, Any]:
    """
    Calcula os deltas e variações comparativas EXPLICITAMENTE entre date_start e date_end.
    
    Regras:
    - date_start e date_end devem ser diferentes (não é permitida a mesma data).
    - O cálculo é sempre: delta = date_end - date_start.
    - Se date_start > date_end, ordena automaticamente garantindo date_start < date_end.
    """
    if not date_start or not date_end:
        return {}

    if date_start == date_end:
        return {"error": "A data inicial e a data final devem ser diferentes para comparação."}

    # Garantir que date_start < date_end
    if date_start > date_end:
        date_start, date_end = date_end, date_start

    snap_start = get_snapshot_by_date(date_start)
    snap_end = get_snapshot_by_date(date_end)

    if not snap_start or not snap_end:
        return {"error": "Um ou ambos os snapshots selecionados não foram localizados."}

    result: Dict[str, Any] = {
        "date_start": date_start,
        "date_end": date_end,
        "start": snap_start,
        "end": snap_end,
        "metrics": {},
        "client_variations": [],
        "error_variations": [],
        "risers": [],
        "fallers": [],
    }

    # 1. Comparação das métricas principais (date_end - date_start)
    for m in ["total_erros", "erros_consulta", "erros_usuario", "erros_nao_classificados", "clientes_afetados"]:
        v_start = snap_start[m]
        v_end = snap_end[m]
        delta_abs = v_end - v_start
        if v_start > 0:
            delta_pct = (delta_abs / v_start) * 100.0
        elif v_end > 0:
            delta_pct = 100.0
        else:
            delta_pct = 0.0

        result["metrics"][m] = {
            "start": v_start,
            "end": v_end,
            "delta_abs": delta_abs,
            "delta_pct": delta_pct,
        }

    # 2. Comparação cliente a cliente
    start_clients_map = {c["cliente"]: c for c in get_client_ranking(snap_start["id"])}
    end_clients_map = {c["cliente"]: c for c in get_client_ranking(snap_end["id"])}
    all_clients = sorted(set(start_clients_map.keys()) | set(end_clients_map.keys()))

    client_vars = []
    risers = []
    fallers = []

    for cli in all_clients:
        c_start = start_clients_map.get(cli)
        c_end = end_clients_map.get(cli)

        t_start = c_start["total_erros"] if c_start else 0
        t_end = c_end["total_erros"] if c_end else 0
        delta_abs = t_end - t_start

        if t_start > 0:
            delta_pct = (delta_abs / t_start) * 100.0
        elif t_end > 0:
            delta_pct = 100.0
        else:
            delta_pct = 0.0

        item = {
            "cliente": cli,
            "total_start": t_start,
            "total_end": t_end,
            "erros_consulta_start": c_start["erros_consulta"] if c_start else 0,
            "erros_consulta_end": c_end["erros_consulta"] if c_end else 0,
            "erros_usuario_start": c_start["erros_usuario"] if c_start else 0,
            "erros_usuario_end": c_end["erros_usuario"] if c_end else 0,
            "erros_nao_classificados_start": c_start["erros_nao_classificados"] if c_start else 0,
            "erros_nao_classificados_end": c_end["erros_nao_classificados"] if c_end else 0,
            "delta_abs": delta_abs,
            "delta_pct": delta_pct,
            "is_new": c_start is None and t_end > 0,
            "is_resolved": t_start > 0 and t_end == 0,
        }

        if t_start > 0 or t_end > 0:
            client_vars.append(item)

        if delta_abs > 0:
            risers.append(item)
        elif delta_abs < 0:
            fallers.append(item)

    client_vars.sort(key=lambda x: (x["total_end"], x["delta_abs"]), reverse=True)
    risers.sort(key=lambda x: x["delta_abs"], reverse=True)
    fallers.sort(key=lambda x: x["delta_abs"])

    result["client_variations"] = client_vars
    result["risers"] = risers
    result["fallers"] = fallers

    # 3. Comparação de tipos de erro entre as duas datas
    start_errors_map = {e["erro"]: e for e in get_top_errors(snap_start["id"])}
    end_errors_map = {e["erro"]: e for e in get_top_errors(snap_end["id"])}
    all_errors = sorted(set(start_errors_map.keys()) | set(end_errors_map.keys()))

    error_vars = []
    for err in all_errors:
        e_s = start_errors_map.get(err)
        e_e = end_errors_map.get(err)

        q_start = e_s["total_quantidade"] if e_s else 0
        q_end = e_e["total_quantidade"] if e_e else 0
        tipo = (e_e["tipo"] if e_e else e_s["tipo"]) if (e_e or e_s) else "nao_classificado"
        d_abs = q_end - q_start

        if q_start > 0:
            d_pct = (d_abs / q_start) * 100.0
        elif q_end > 0:
            d_pct = 100.0
        else:
            d_pct = 0.0

        error_vars.append(
            {
                "erro": err,
                "tipo": tipo,
                "qtd_start": q_start,
                "qtd_end": q_end,
                "delta_abs": d_abs,
                "delta_pct": d_pct,
                "clientes_start": e_s["clientes_afetados"] if e_s else 0,
                "clientes_end": e_e["clientes_afetados"] if e_e else 0,
            }
        )

    error_vars.sort(key=lambda x: (x["qtd_end"], x["delta_abs"]), reverse=True)
    result["error_variations"] = error_vars

    return result


def get_period_data(date_start: str, date_end: str) -> Dict[str, Any]:
    """
    Consolida métricas e série histórica de um período delimitado pelo usuário.
    
    Regras:
    - Consulta somente os snapshots no intervalo [date_start, date_end].
    - Não interpola nem inventa dados para dias sem snapshot.
    - Total Clientes Únicos: quantidade de clientes distintos em todo o período (COUNT DISTINCT).
    """
    if not date_start or not date_end:
        return {}

    d_start, d_end = (date_start, date_end) if date_start <= date_end else (date_end, date_start)
    snapshots = get_snapshots_evolution(date_start=d_start, date_end=d_end)

    if not snapshots:
        return {
            "date_start": d_start,
            "date_end": d_end,
            "snapshots": [],
            "dias_com_snapshot": 0,
            "total_erros_periodo": 0,
            "erros_consulta_periodo": 0,
            "erros_usuario_periodo": 0,
            "erros_nao_classificados_periodo": 0,
            "total_clientes_unicos": 0,
            "media_diaria_erros": 0.0,
            "dia_pico": None,
            "client_ranking": [],
            "top_errors": [],
        }

    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()

        # 1. Total Clientes Únicos (COUNT DISTINCT cliente no período)
        cursor.execute(
            """
            SELECT COUNT(DISTINCT c.cliente) AS total_unicos
            FROM daily_clientes c
            JOIN daily_snapshots s ON c.snapshot_id = s.id
            WHERE s.data >= ? AND s.data <= ? AND c.total_erros > 0
            """,
            (d_start, d_end),
        )
        total_clientes_unicos = cursor.fetchone()["total_unicos"] or 0

        # 2. Ranking consolidado de clientes no período
        cursor.execute(
            """
            SELECT 
                c.cliente, 
                SUM(c.total_erros) AS total_erros, 
                SUM(c.erros_consulta) AS erros_consulta, 
                SUM(c.erros_usuario) AS erros_usuario, 
                SUM(c.erros_nao_classificados) AS erros_nao_classificados,
                COUNT(DISTINCT s.data) AS dias_com_erro
            FROM daily_clientes c
            JOIN daily_snapshots s ON c.snapshot_id = s.id
            WHERE s.data >= ? AND s.data <= ?
            GROUP BY c.cliente
            ORDER BY total_erros DESC, c.cliente ASC
            """,
            (d_start, d_end),
        )
        client_ranking = [dict(row) for row in cursor.fetchall()]

        # 3. Ranking consolidado de erros no período
        cursor.execute(
            """
            SELECT 
                e.erro, 
                e.tipo, 
                SUM(e.quantidade) AS total_quantidade, 
                COUNT(DISTINCT s.data) AS dias_presente,
                COUNT(DISTINCT e.cliente) AS clientes_afetados
            FROM daily_erros e
            JOIN daily_snapshots s ON e.snapshot_id = s.id
            WHERE s.data >= ? AND s.data <= ?
            GROUP BY e.erro, e.tipo
            ORDER BY total_quantidade DESC, dias_presente DESC
            """,
            (d_start, d_end),
        )
        top_errors = [dict(row) for row in cursor.fetchall()]

    dias_com_snapshot = len(snapshots)
    total_erros_periodo = sum(s["total_erros"] for s in snapshots)
    erros_consulta_periodo = sum(s["erros_consulta"] for s in snapshots)
    erros_usuario_periodo = sum(s["erros_usuario"] for s in snapshots)
    erros_nao_classificados_periodo = sum(s["erros_nao_classificados"] for s in snapshots)
    media_diaria = total_erros_periodo / dias_com_snapshot if dias_com_snapshot > 0 else 0.0
    dia_pico = max(snapshots, key=lambda s: s["total_erros"]) if snapshots else None

    return {
        "date_start": d_start,
        "date_end": d_end,
        "snapshots": snapshots,
        "dias_com_snapshot": dias_com_snapshot,
        "total_erros_periodo": total_erros_periodo,
        "erros_consulta_periodo": erros_consulta_periodo,
        "erros_usuario_periodo": erros_usuario_periodo,
        "erros_nao_classificados_periodo": erros_nao_classificados_periodo,
        "total_clientes_unicos": total_clientes_unicos,
        "media_diaria_erros": media_diaria,
        "dia_pico": dia_pico,
        "client_ranking": client_ranking,
        "top_errors": top_errors,
    }
