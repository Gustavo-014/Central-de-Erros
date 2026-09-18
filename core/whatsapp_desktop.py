import os
import time
from typing import Tuple
import pyautogui
import pyperclip

# Desativa o fail-safe por segurança de coordenadas
pyautogui.FAILSAFE = False


def open_group_in_whatsapp_desktop(
    group_name: str, message: str = "", wait_open_seconds: float = 2.0
) -> Tuple[bool, str]:
    """
    Abre o WhatsApp Desktop, ativa o campo de pesquisa, busca o grupo pelo nome,
    abre a conversa e cola a mensagem na caixa de digitação (sem disparar envio).
    
    :param group_name: Nome cadastrado do grupo no WhatsApp
    :param message: Mensagem a ser colada
    :param wait_open_seconds: Tempo de espera para o WhatsApp carregar e subir na tela
    """
    if not group_name or not str(group_name).strip():
        return False, "Nome do grupo não informado."

    group_name = str(group_name).strip()

    try:
        # 1. Garante que a mensagem já esteja na área de transferência por segurança
        if message and str(message).strip():
            pyperclip.copy(str(message).strip())

        # 2. Abre ou traz o WhatsApp Desktop para primeiro plano via protocolo nativo do Windows
        os.startfile("whatsapp:")

        # Aguarda a tela do WhatsApp abrir e se consolidar
        time.sleep(wait_open_seconds)

        # 3. Pressiona ESC para fechar qualquer modal, menu ou foco residual e garantir estado limpo
        pyautogui.press("esc")
        time.sleep(0.3)

        # 4. Aciona a busca de conversas do WhatsApp (Ctrl + F)
        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.5)

        # 5. Garante que o campo de busca esteja limpo antes de colar o grupo
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        pyautogui.press("backspace")
        time.sleep(0.1)

        # 6. Copia o nome do grupo e cola no campo de busca
        pyperclip.copy(group_name)
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "v")

        # Aguarda o WhatsApp pesquisar e filtrar as conversas na lista
        time.sleep(1.0)

        # 7. Pressiona ENTER para abrir a primeira conversa correspondente encontrada
        pyautogui.press("enter")

        # Aguarda o chat carregar na tela e o cursor focar no campo de digitação
        time.sleep(0.8)

        # 8. Garante a mensagem na área de transferência e cola no chat
        if message and str(message).strip():
            pyperclip.copy(str(message).strip())
            time.sleep(0.2)
            pyautogui.hotkey("ctrl", "v")

        return True, f"WhatsApp Desktop focado no grupo '{group_name}' com a mensagem pronta!"

    except Exception as e:
        return False, f"Erro ao acionar automação do WhatsApp Desktop: {str(e)}"
