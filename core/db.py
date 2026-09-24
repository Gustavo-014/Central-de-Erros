import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple


from contextlib import contextmanager


def get_db_path() -> Path:
    """Retorna o caminho para o arquivo SQLite de histórico e contatos."""
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir / "history.db"


@contextmanager
def get_connection():
    """Retorna um gerenciador de contexto para conexão SQLite com foreign keys habilitadas e fechamento garantido."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


_DB_INITIALIZED = False


def init_db(force: bool = False) -> None:
    """Inicializa as tabelas necessárias no SQLite se não existirem."""
    global _DB_INITIALIZED
    if _DB_INITIALIZED and not force:
        return

    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Tabela de Contatos/Grupos de Clientes
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS client_contacts (
                client_name TEXT PRIMARY KEY,
                contact_type TEXT NOT NULL, -- 'group_name', 'phone' ou 'group_link'
                contact_value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        
        # Tabela de Histórico de Mensagens Enviadas
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sent_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT NOT NULL,
                error_normalized TEXT NOT NULL,
                identifiers TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                channel TEXT DEFAULT 'whatsapp'
            )
            """
        )
        
        # Índices para performance nas consultas de duplicidade
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_sent_history_lookup 
            ON sent_history (client_name, error_normalized, sent_at)
            """
        )

        # 1. Tabela Principal de Snapshots Diários
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL UNIQUE,          -- 'YYYY-MM-DD'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                file_name TEXT,                     -- Informativo
                file_hash TEXT NOT NULL,            -- SHA-256 do arquivo
                total_erros INTEGER NOT NULL DEFAULT 0,
                erros_consulta INTEGER NOT NULL DEFAULT 0,
                erros_usuario INTEGER NOT NULL DEFAULT 0,
                erros_nao_classificados INTEGER NOT NULL DEFAULT 0,
                clientes_afetados INTEGER NOT NULL DEFAULT 0
            )
            """
        )

        # 2. Indicadores Consolidados por Cliente (com UNIQUE)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                cliente TEXT NOT NULL,
                total_erros INTEGER NOT NULL DEFAULT 0,
                erros_consulta INTEGER NOT NULL DEFAULT 0,
                erros_usuario INTEGER NOT NULL DEFAULT 0,
                erros_nao_classificados INTEGER NOT NULL DEFAULT 0,
                -- Campos reservados para futura evolução operacional:
                cliente_comunicado INTEGER DEFAULT 0,
                data_ultimo_contato TEXT,
                qtd_fups INTEGER DEFAULT 0,
                proxima_acao TEXT,
                responsavel TEXT,
                prazo TEXT,
                risco TEXT,
                status TEXT DEFAULT 'pendente',
                intervencao_lideranca INTEGER DEFAULT 0,
                FOREIGN KEY (snapshot_id) REFERENCES daily_snapshots(id) ON DELETE CASCADE,
                UNIQUE(snapshot_id, cliente)
            )
            """
        )

        # 3. Detalhamento de Erros por Cliente (com UNIQUE)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_erros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                cliente TEXT NOT NULL,
                erro TEXT NOT NULL,
                tipo TEXT NOT NULL,                 -- 'consulta', 'usuario' ou 'nao_classificado'
                quantidade INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (snapshot_id) REFERENCES daily_snapshots(id) ON DELETE CASCADE,
                UNIQUE(snapshot_id, cliente, erro, tipo)
            )
            """
        )

        # Índices de performance para Daily
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_snapshots_data ON daily_snapshots(data)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_snapshots_hash ON daily_snapshots(file_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_clientes_snapshot ON daily_clientes(snapshot_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_clientes_cliente ON daily_clientes(cliente)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_erros_snapshot ON daily_erros(snapshot_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_erros_cliente ON daily_erros(snapshot_id, cliente)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_erros_erro ON daily_erros(erro)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_erros_tipo ON daily_erros(tipo)")

        conn.commit()
    _DB_INITIALIZED = True


def reset_daily_db() -> None:
    """
    Remove exclusivamente as tabelas da funcionalidade Daily (daily_erros, daily_clientes, daily_snapshots)
    e as recria via init_db(), preservando intactos client_contacts e sent_history.
    ATENÇÃO: Deve ser chamado apenas para resets manuais ou rotinas de migração controladas,
    NUNCA na inicialização normal do Streamlit.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS daily_erros")
        cursor.execute("DROP TABLE IF EXISTS daily_clientes")
        cursor.execute("DROP TABLE IF EXISTS daily_snapshots")
        conn.commit()
    init_db(force=True)


def sanitize_phone(phone: str) -> str:
    """Extrai somente dígitos e garante código do país (DDI 55 por padrão se ausente)."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) in (10, 11):  # DDD + Número (ex: 11999998888)
        digits = "55" + digits
    return digits


def get_all_contacts() -> Dict[str, Dict[str, str]]:
    """Retorna um dicionário com todos os contatos cadastrados {cliente: {type, value, updated_at}}."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT client_name, contact_type, contact_value, updated_at FROM client_contacts ORDER BY client_name")
        rows = cursor.fetchall()
        return {
            row["client_name"]: {
                "contact_type": row["contact_type"],
                "contact_value": row["contact_value"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        }


def get_client_contact(client_name: str) -> Optional[Dict[str, str]]:
    """Busca o contato cadastrado para um cliente específico."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT contact_type, contact_value, updated_at FROM client_contacts WHERE client_name = ?",
            (client_name.strip(),)
        )
        row = cursor.fetchone()
        if row:
            return {
                "contact_type": row["contact_type"],
                "contact_value": row["contact_value"],
                "updated_at": row["updated_at"],
            }
        return None


def save_client_contact(client_name: str, contact_value: str, *args, **kwargs) -> Tuple[bool, str]:
    """
    Cadastra ou atualiza o contato/grupo do cliente.
    contact_type: 'group_name' (Nome do grupo), 'phone' (Telefone) ou 'group_link' (Link de convite)
    """
    init_db()
    client_name = str(client_name).strip()
    contact_value = str(contact_value).strip()

    contact_type = args[0] if args else kwargs.get("contact_type", "group_name")

    if not client_name:
        return False, "O nome do cliente não pode estar vazio."
    if not contact_value:
        return False, "O nome do grupo ou contato não pode estar vazio."

    # Detecção automática ou validação pelo tipo
    if contact_type == "phone":
        clean_value = sanitize_phone(contact_value)
        if len(clean_value) < 10:
            return False, "Número de telefone inválido. Informe DDD + Número."
    elif "chat.whatsapp.com" in contact_value.lower() or contact_value.startswith("http"):
        contact_type = "group_link"
        clean_value = contact_value
    else:
        # Padrão: Nome do grupo no WhatsApp
        contact_type = "group_name"
        clean_value = contact_value

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO client_contacts (client_name, contact_type, contact_value, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(client_name) DO UPDATE SET
                contact_type = excluded.contact_type,
                contact_value = excluded.contact_value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (client_name, contact_type, clean_value)
        )
        conn.commit()

    return True, "Contato/Grupo salvo com sucesso!"


def delete_client_contact(client_name: str) -> None:
    """Exclui o contato cadastrado de um cliente."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM client_contacts WHERE client_name = ?", (client_name.strip(),))
        conn.commit()


def register_sent_message(client_name: str, error_normalized: str, identifiers: str = "", channel: str = "whatsapp") -> None:
    """Registra o envio de uma mensagem no histórico."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO sent_history (client_name, error_normalized, identifiers, sent_at, channel)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
            """,
            (client_name.strip(), error_normalized.strip(), identifiers.strip(), channel)
        )
        conn.commit()


def register_client_all_errors_sent(client_name: str, errors: List[str], channel: str = "whatsapp") -> None:
    """Registra todos os erros enviados para um cliente em lote."""
    init_db()
    with get_connection() as conn:
        cursor = conn.cursor()
        for err in errors:
            cursor.execute(
                """
                INSERT INTO sent_history (client_name, error_normalized, sent_at, channel)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?)
                """,
                (client_name.strip(), err.strip(), channel)
            )
        conn.commit()


def get_recent_sent_history(client_name: str, days: int = 1) -> List[Dict[str, str]]:
    """Retorna o histórico de mensagens enviadas para o cliente nos últimos X dias (padrão: 1 dia)."""
    init_db()
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT error_normalized, identifiers, sent_at, channel 
            FROM sent_history 
            WHERE client_name = ? AND sent_at >= ?
            ORDER BY sent_at DESC
            """,
            (client_name.strip(), cutoff_date)
        )
        rows = cursor.fetchall()
        return [
            {
                "error_normalized": row["error_normalized"],
                "identifiers": row["identifiers"],
                "sent_at": row["sent_at"],
                "channel": row["channel"],
            }
            for row in rows
        ]


def check_errors_sent_recently(client_name: str, errors: List[str], days: int = 1) -> Dict[str, Optional[Dict[str, str]]]:
    """
    Para uma lista de erros de um cliente, retorna um dicionário {erro: {'sent_at': ..., 'channel': ...} ou None}
    indicando quais erros já foram enviados ou resolvidos dentro do período de cooldown de 1 dia.
    """
    init_db()
    result: Dict[str, Optional[Dict[str, str]]] = {err: None for err in errors}
    if not errors or not client_name:
        return result

    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    placeholders = ",".join("?" for _ in errors)
    query = f"""
        SELECT error_normalized, sent_at, channel 
        FROM sent_history 
        WHERE client_name = ? AND error_normalized IN ({placeholders}) AND sent_at >= ?
        ORDER BY sent_at DESC
    """
    params = [client_name.strip()] + [e.strip() for e in errors] + [cutoff_date]

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        for row in cursor.fetchall():
            err_norm = row["error_normalized"]
            if err_norm in result and result[err_norm] is None:
                result[err_norm] = {
                    "sent_at": row["sent_at"],
                    "channel": row["channel"] or "whatsapp",
                }

    return result


def get_all_recent_cooldowns(days: int = 1) -> Dict[Tuple[str, str], Dict[str, str]]:
    """
    Retorna um mapa {(client_name, error_normalized): {'sent_at': ..., 'channel': ...}}
    com todos os erros enviados/resolvidos recentemente em uma única query rápida.
    """
    init_db()
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    result: Dict[Tuple[str, str], Dict[str, str]] = {}

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT client_name, error_normalized, sent_at, channel
            FROM sent_history
            WHERE sent_at >= ?
            ORDER BY sent_at DESC
            """,
            (cutoff_date,)
        )
        for row in cursor.fetchall():
            key = (row["client_name"].strip(), row["error_normalized"].strip())
            if key not in result:
                result[key] = {
                    "sent_at": row["sent_at"],
                    "channel": row["channel"] or "whatsapp",
                }

    return result

