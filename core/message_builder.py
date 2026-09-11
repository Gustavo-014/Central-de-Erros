import re
from typing import Dict, List

from core.template_loader import load_layout, load_templates
from core.utils import normalize_text as _base_normalize


def _normalize_text(value: str) -> str:
    """Normaliza texto para comparação tolerante em relação a formatação."""
    return _base_normalize(value).casefold()


def _format_orientations(orientations: List[str]) -> List[str]:
    """Formata a lista de orientações, separando introduções, alertas e links de itens com marcadores."""
    if not orientations:
        return []

    # Se houver apenas uma linha de orientação, exibe como texto simples (sem marcador)
    if len(orientations) == 1:
        cleaned = re.sub(r"^(?:-\s*|•\s*)", "", orientations[0].strip())
        return [cleaned] if cleaned else []

    formatted_lines: List[str] = []
    is_in_bullet_list = False

    for item in orientations:
        cleaned = item.strip()
        if not cleaned:
            continue

        # Remove marcadores existentes no início para padronizar
        cleaned_no_bullet = re.sub(r"^(?:-\s*|•\s*)", "", cleaned).strip()

        # Se termina com :. corrige para :
        if cleaned_no_bullet.endswith(":."):
            cleaned_no_bullet = cleaned_no_bullet[:-2] + ":"

        # Links, alertas ou frases introdutórias terminadas em ':'
        if (
            cleaned.startswith("http://")
            or cleaned.startswith("https://")
            or cleaned.startswith("⚠️")
            or cleaned_no_bullet.endswith(":")
        ):
            formatted_lines.append(cleaned_no_bullet)
            is_in_bullet_list = cleaned_no_bullet.endswith(":")
        elif is_in_bullet_list:
            formatted_lines.append(f"• {cleaned_no_bullet}")
        else:
            # Texto explicativo geral (ex: 'Para auxiliar, vamos encaminhar...')
            if cleaned.startswith("-") or cleaned.startswith("•"):
                formatted_lines.append(f"• {cleaned_no_bullet}")
            else:
                formatted_lines.append(cleaned_no_bullet)

    return formatted_lines


def _format_identifiers(occurrence: Dict[str, str], fields: List[str]) -> str:
    """Formata os identificadores de uma ocorrência conforme a ordem definida nos campos de exibição."""
    values: List[str] = []
    for field in fields:
        value = occurrence.get(field)
        if value:
            if field == "cnpj":
                value = value.replace(".", "").replace("/", "").replace("-", "")
                if len(value) == 14:
                    value = f"{value[:2]}.{value[2:5]}.{value[5:8]}/{value[8:12]}-{value[12:14]}"
            values.append(value)
    return " - ".join(values)


def build_messages(processed_data: Dict[str, Dict[str, List[Dict[str, str]]]]) -> Dict[str, str]:
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

        for index, (erro, ocorrencias) in enumerate(erros.items(), start=1):
            normalized_error = _normalize_text(erro)
            template = normalized_templates.get(normalized_error)
            title = template.get("titulo", erro) if template is not None else erro
            identifier_label = template.get("rotulo_identificadores", "Identificadores") if template is not None else "Identificadores"

            lines.append(f"{index} - {title}")
            lines.append("")

            if template is None:
                lines.append("Mensagem para este erro ainda não cadastrada.")
            else:
                if template.get("impacto"):
                    lines.append("Impacto:")
                    lines.append(template.get("impacto", ""))
                    lines.append("")

                lines.append(f"{identifier_label}:")
                for occurrence in ocorrencias:
                    fields = template.get("campos_exibicao", ["placa"])
                    formatted_value = _format_identifiers(occurrence, fields)
                    if formatted_value:
                        lines.append(formatted_value)
                lines.append("")

                orientation_lines = _format_orientations(template.get("orientacao", []))
                lines.extend(orientation_lines)

            lines.append("")

        lines.append(layout.get("rodape", ""))
        messages[cliente] = "\n".join(line for line in lines if line is not None)

    return messages
