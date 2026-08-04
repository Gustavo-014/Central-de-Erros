from typing import Any, Dict, List

from core.template_loader import load_layout, load_templates


def build_messages(processed_data: Dict[str, Dict[str, List[str]]]) -> Dict[str, str]:
    """Gera mensagens completas para cada cliente com base em templates e layout salvos em JSON."""
    templates = load_templates()
    layout = load_layout()

    messages: Dict[str, str] = {}

    for cliente, erros in processed_data.items():
        lines: List[str] = []
        lines.append(layout.get("cabecalho", ""))

        for index, (erro, placas) in enumerate(erros.items(), start=1):
            template = templates.get(erro)

            lines.append(f"{index} - {erro}")
            lines.append("")
            lines.append("Placas:")
            lines.append(", ".join(placas))
            lines.append("")

            if template is None:
                lines.append("Mensagem para este erro ainda não cadastrada.")
            else:
                lines.append("Impacto")
                lines.append(template.get("impacto", ""))
                lines.append("")
                lines.append("Solicitamos que verifiquem:")
                for orientacao in template.get("orientacao", []):
                    lines.append(f"• {orientacao}")

            lines.append("")

        lines.append(layout.get("rodape", ""))
        messages[cliente] = "\n".join(line for line in lines if line is not None)

    return messages
