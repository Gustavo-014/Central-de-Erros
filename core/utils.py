import re


def normalize_text(value: str) -> str:
    """Normaliza texto removendo espaços extras e pontuação de formatação no final."""
    normalized = re.sub(r"\s+", " ", value.strip())
    if normalized.endswith("."):
        normalized = normalized[:-1]
    return normalized
