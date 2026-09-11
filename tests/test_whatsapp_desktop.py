import unittest
from unittest.mock import patch, MagicMock
from core.whatsapp_desktop import open_group_in_whatsapp_desktop


class TestWhatsAppDesktop(unittest.TestCase):
    def test_empty_group_name(self):
        ok, msg = open_group_in_whatsapp_desktop("")
        self.assertFalse(ok)
        self.assertIn("não informado", msg)

        ok, msg = open_group_in_whatsapp_desktop("   ")
        self.assertFalse(ok)

    @patch("core.whatsapp_desktop.time.sleep")
    @patch("core.whatsapp_desktop.pyautogui.hotkey")
    @patch("core.whatsapp_desktop.pyautogui.press")
    @patch("core.whatsapp_desktop.pyperclip.copy")
    @patch("core.whatsapp_desktop.os.startfile")
    def test_successful_open(self, mock_startfile, mock_pyperclip, mock_press, mock_hotkey, mock_sleep):
        ok, msg = open_group_in_whatsapp_desktop("Frota ABC - Suporte", "Olá, temos um erro pendente.")
        self.assertTrue(ok)
        self.assertIn("Frota ABC - Suporte", msg)

        # Deve ter chamado os.startfile("whatsapp:")
        mock_startfile.assert_called_once_with("whatsapp:")

        # Deve ter pressionado ESC e ENTER
        mock_press.assert_any_call("esc")
        mock_press.assert_any_call("enter")

        # Deve ter acionado Ctrl+F e Ctrl+V
        mock_hotkey.assert_any_call("ctrl", "f")
        mock_hotkey.assert_any_call("ctrl", "v")

        # Deve ter copiado tanto o grupo quanto a mensagem
        self.assertEqual(mock_pyperclip.call_count, 2)
        mock_pyperclip.assert_any_call("Frota ABC - Suporte")
        mock_pyperclip.assert_any_call("Olá, temos um erro pendente.")


if __name__ == "__main__":
    unittest.main()
