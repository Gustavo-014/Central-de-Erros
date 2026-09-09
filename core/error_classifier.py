import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core.template_loader import load_templates
from core.utils import normalize_text


def _load_optional_error_types() -> Dict[str, str]:
    """Carrega mapeamento opcional adicional de types se o arquivo error_types.json existir."""
    file_path = Path(__file__).resolve().parent.parent / "data" / "error_types.json"
    if file_path.exists():
        try:
            with file_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


# Palavras-chave para inferência quando não constar em template/configuração
CONSULTA_KEYWORDS = [
    "instabilidade",
    "captcha",
    "timeout",
    "conexao",
    "conexão",
    "indisponivel",
    "indisponível",
    "servidor",
    "500",
    "502",
    "503",
    "504",
    "nao encontrado",
    "não encontrado",
    "nao localizado",
    "não localizado",
    "nao consta",
    "não consta",
    "sem debitos",
    "sem débitos",
    "nao cadastrado",
    "não cadastrado",
]

USUARIO_KEYWORDS = [
    "senha",
    "usuario",
    "usuário",
    "2fa",
    "etapas",
    "adesao",
    "adesão",
    "sne",
    "certificado",
    "cnpj",
    "cpf",
    "crv",
    "proprietario",
    "proprietário",
    "bloqueado",
    "protegido",
    "liberar",
    "credenciais",
    "invalido",
    "inválido",
]


def classify_error(
    error_name: str,
    raw_row: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """
    Classifica um erro entre 'consulta', 'usuario' ou 'nao_classificado'.
    
    Retorna uma tupla: (tipo, metodo_classificacao)
    onde metodo_classificacao pode ser:
    - 'coluna_planilha'
    - 'template'
    - 'error_types_json'
    - 'palavras_chave'
    - 'nao_classificado'
    """
    # 1. Coluna explícita da planilha
    if raw_row and isinstance(raw_row, dict):
        for col_candidate in ["tipo", "tipo de erro", "tipo do erro", "tipo_erro", "categoria", "tipo erro"]:
            for key, val in raw_row.items():
                if str(key).strip().lower() == col_candidate and val is not None:
                    val_str = str(val).strip().lower()
                    if "consulta" in val_str:
                        return "consulta", "coluna_planilha"
                    if "usuario" in val_str or "usuário" in val_str:
                        return "usuario", "coluna_planilha"

    error_clean = normalize_text(str(error_name or "")).casefold()
    if not error_clean:
        return "nao_classificado", "nao_classificado"

    # 2. templates.json (fonte oficial de templates do sistema)
    templates = load_templates()
    for tmpl_key, tmpl_data in templates.items():
        if normalize_text(tmpl_key).casefold() == error_clean:
            tipo = tmpl_data.get("tipo")
            if tipo in ["consulta", "usuario"]:
                return tipo, "template"

    # 3. data/error_types.json (catálogo adicional opcional)
    extra_types = _load_optional_error_types()
    for err_key, tipo_val in extra_types.items():
        if normalize_text(err_key).casefold() == error_clean:
            if tipo_val in ["consulta", "usuario"]:
                return tipo_val, "error_types_json"

    # 4. Regras contextuais por palavras-chave
    for kw in CONSULTA_KEYWORDS:
        if kw in error_clean:
            return "consulta", "palavras_chave"

    for kw in USUARIO_KEYWORDS:
        if kw in error_clean:
            return "usuario", "palavras_chave"

    # 5. Fallback seguro
    return "nao_classificado", "nao_classificado"
