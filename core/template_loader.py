import json
from pathlib import Path
from typing import Any, Dict

import streamlit as st


@st.cache_data
def load_templates() -> Dict[str, Any]:
    """Carrega os templates de erro a partir do arquivo JSON."""
    templates_path = Path(__file__).resolve().parent.parent / "data" / "templates.json"

    with templates_path.open("r", encoding="utf-8") as file:
        return json.load(file)


@st.cache_data
def load_layout() -> Dict[str, str]:
    """Carrega o layout das mensagens a partir do arquivo JSON."""
    layout_path = Path(__file__).resolve().parent.parent / "data" / "layout.json"

    with layout_path.open("r", encoding="utf-8") as file:
        return json.load(file)
