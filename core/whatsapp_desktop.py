import os
import time
from typing import Tuple
import pyautogui
import pyperclip

# Desativa o fail-safe por segurança de coordenadas
pyautogui.FAILSAFE = False


def open_group_in_whatsapp_desktop(group_name: str, message: str = "") -> Tuple[bool, str]:
    """
    Abre o WhatsApp Desktop, ativa o campo de pesquisa, busca o grupo pelo nome,
    abre a conversa e cola a mensagem na caixa de digitação (sem disparar envio).
    """
    if not group_name or not str(group_name).strip():
        return False, "Nome do grupo não informado."

    group_name = str(group_name).strip()

    try:
        # 1. Copia o nome do grupo para a área de transferência com antecedência
        pyperclip.copy(group_name)

        # 2. Abre ou traz o WhatsApp Desktop para primeiro plano via protocolo nativo
        os.startfile("whatsapp:")
        # Aguarda a janela subir na tela e se tornar ativa
        time.sleep(1.2)

        # 3. Pressiona ESC para fechar qualquer modal ou foco residual e garantir estado limpo
        pyautogui.press("esc")
        time.sleep(0.3)

        # 4. Aciona a busca de conversas do WhatsApp (Ctrl + F)
        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.5)

        # 5. Cola o nome do grupo no campo de busca
        pyautogui.hotkey("ctrl", "v")
        # Aguarda o WhatsApp pesquisar e listar as conversas
        time.sleep(1.0)

        # 6. Pressiona ENTER para abrir a primeira conversa correspondente encontrada
        pyautogui.press("enter")
        # Aguarda o chat carregar na tela e o cursor focar no campo de digitação
        time.sleep(0.8)

        # 7. Se houver mensagem, copia e cola no chat
        if message and str(message).strip():
            pyperclip.copy(str(message).strip())
            time.sleep(0.2)
            pyautogui.hotkey("ctrl", "v")

        return True, f"WhatsApp Desktop aberto no grupo '{group_name}' com a mensagem pronta!"

    except Exception as e:
        return False, f"Erro ao acionar automação do WhatsApp Desktop: {str(e)}"
