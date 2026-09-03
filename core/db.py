import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def get_db_path() -> Path:
    """Retorna o caminho para o arquivo SQLite de histórico e contatos."""
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir / "history.db"


def get_connection() -> sqlite3.Connection:
    """Retorna uma conexão com o banco de dados SQLite."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Inicializa as tabelas necessárias no SQLite se não existirem."""
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
        conn.commit()


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


def check_errors_sent_recently(client_name: str, errors: List[str], days: int = 1) -> Dict[str, Optional[str]]:
    """
    Para uma lista de erros de um cliente, retorna um dicionário {erro: data_ultimo_envio ou None}
    indicando quais erros já foram enviados dentro do período de cooldown de 1 dia.
    """
    init_db()
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    result: Dict[str, Optional[str]] = {err: None for err in errors}

    with get_connection() as conn:
        cursor = conn.cursor()
        for err in errors:
            cursor.execute(
                """
                SELECT sent_at 
                FROM sent_history 
                WHERE client_name = ? AND error_normalized = ? AND sent_at >= ?
                ORDER BY sent_at DESC 
                LIMIT 1
                """,
                (client_name.strip(), err.strip(), cutoff_date)
            )
            row = cursor.fetchone()
            if row:
                result[err] = row["sent_at"]

    return result
