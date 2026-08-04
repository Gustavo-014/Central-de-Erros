import json
from pathlib import Path
from typing import Dict, List


def build_messages(processed_data: Dict[str, Dict[str, List[str]]]) -> Dict[str, str]:
    """Gera mensagens completas para cada cliente com base em templates salvos em JSON."""
    templates_path = Path(__file__).resolve().parent.parent / "data" / "templates.json"

    with templates_path.open("r", encoding="utf-8") as file:
        templates = json.load(file)

    messages: Dict[str, str] = {}

    for cliente, erros in processed_data.items():
        lines: List[str] = []
        lines.append("Olá, tudo bem?")
        lines.append("")
        lines.append("Durante a última rodada identificamos os seguintes retornos de erro para os veículos:")
        lines.append("")

        for index, (erro, placas) in enumerate(erros.items(), start=1):
            lines.append(f"{index}. {erro}")
            lines.append(f"Placas: {', '.join(placas)}")
            template = templates.get(erro, "Mensagem para este erro ainda não cadastrada.")
            lines.append(template)
            lines.append("")

        lines.append("Caso tenham qualquer dúvida, estamos à disposição.")
        lines.append("Equipe Brobot")
        messages[cliente] = "\n".join(lines)

    return messages
