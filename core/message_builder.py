import re
from typing import Dict, List

from core.template_loader import load_layout, load_templates


def _normalize_text(value: str) -> str:
    """Normaliza texto para comparação tolerante em relação a formatação."""
    normalized = re.sub(r"\s+", " ", value.strip())
    if normalized.endswith("."):
        normalized = normalized[:-1]
    return normalized.casefold()


def _clean_orientation_text(value: str) -> str:
    """Remove marcadores e a frase padrão de orientações para exibição limpa."""
    cleaned = value.strip()
    cleaned = re.sub(r"^(?:-\s*|•\s*)", "", cleaned)
    cleaned = re.sub(r"^Solicitamos que verifiquem:\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def build_messages(processed_data: Dict[str, Dict[str, List[str]]]) -> Dict[str, str]:
    """Gera mensagens completas para cada cliente com base em templates e layout salvos em JSON."""
    templates = load_templates()
    layout = load_layout()
    normalized_templates = {
        _normalize_text(key): value for key, value in templates.items()
    }

    messages: Dict[str, str] = {}

    for cliente, erros in processed_data.items():
        lines: List[str] = []
        lines.append(layout.get("cabecalho", ""))

        for index, (erro, placas) in enumerate(erros.items(), start=1):
            normalized_error = _normalize_text(erro)
            template = normalized_templates.get(normalized_error)
            title = template.get("titulo", erro) if template is not None else erro

            lines.append(f"{index} - {title}")
            lines.append("")
            lines.append("Placas:")
            for placa in placas:
                lines.append(placa)
            lines.append("")

            if template is None:
                lines.append("Mensagem para este erro ainda não cadastrada.")
            else:
                lines.append("Impacto:")
                lines.append(template.get("impacto", ""))
                lines.append("")
                lines.append("Solicitamos que verifiquem:")
                for orientacao in template.get("orientacao", []):
                    cleaned_orientation = _clean_orientation_text(orientacao)
                    if cleaned_orientation:
                        lines.append(f"• {cleaned_orientation}")

            lines.append("")

        lines.append(layout.get("rodape", ""))
        messages[cliente] = "\n".join(line for line in lines if line is not None)

    return messages
