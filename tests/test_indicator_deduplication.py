import unittest
import pandas as pd

from core.processor import process_dataframe
from core.message_builder import build_messages


class TestIndicatorDeduplication(unittest.TestCase):
    def test_same_cnpj_repeated_three_times_in_same_error(self):
        """Mesmo CNPJ repetido 3 vezes no mesmo erro → deve aparecer 1 vez."""
        df = pd.DataFrame([
            {
                "Nome da Conta": "Cliente Teste",
                "Mensagem de Erro": "CNPJ não vinculado ao gov.br",
                "CNPJ": "12123123000101",
                "Placa": "ABC1111",
                "Renavam": "11111111111",
            },
            {
                "Nome da Conta": "Cliente Teste",
                "Mensagem de Erro": "CNPJ não vinculado ao gov.br",
                "CNPJ": "12.123.123/0001-01",
                "Placa": "DEF2222",
                "Renavam": "22222222222",
            },
            {
                "Nome da Conta": "Cliente Teste",
                "Mensagem de Erro": "CNPJ não vinculado ao gov.br",
                "CNPJ": "12123123000101",
                "Placa": "GHI3333",
                "Renavam": "33333333333",
            },
        ])

        dados, _ = process_dataframe(df)
        self.assertIn("Cliente Teste", dados)
        erros_cliente = dados["Cliente Teste"]
        
        self.assertIn("CNPJ não vinculado ao gov.br", erros_cliente)
        ocorrencias = erros_cliente["CNPJ não vinculado ao gov.br"]
        self.assertEqual(len(ocorrencias), 1)
        self.assertEqual(ocorrencias[0]["cnpj"], "12.123.123/0001-01")

        mensagens = build_messages(dados)
        msg = mensagens["Cliente Teste"]
        self.assertEqual(msg.count("12.123.123/0001-01"), 1)

    def test_same_cnpj_in_two_different_errors(self):
        """Mesmo CNPJ em 2 erros diferentes → deve aparecer 1 vez em cada erro."""
        df = pd.DataFrame([
            {
                "Nome da Conta": "Cliente Teste",
                "Mensagem de Erro": "CNPJ não vinculado ao gov.br",
                "CNPJ": "12.123.123/0001-01",
                "Placa": "ABC1111",
            },
            {
                "Nome da Conta": "Cliente Teste",
                "Mensagem de Erro": "CNPJ não vinculado ao gov.br",
                "CNPJ": "12.123.123/0001-01",
                "Placa": "DEF2222",
            },
            {
                "Nome da Conta": "Cliente Teste",
                "Mensagem de Erro": "Certificado Digital expirado. Por favor, utilize um novo",
                "CNPJ": "12.123.123/0001-01",
                "Placa": "GHI3333",
            },
        ])

        dados, _ = process_dataframe(df)
        erros_cliente = dados["Cliente Teste"]

        self.assertEqual(len(erros_cliente["CNPJ não vinculado ao gov.br"]), 1)
        self.assertEqual(len(erros_cliente["Certificado Digital expirado. Por favor, utilize um novo"]), 1)

        mensagens = build_messages(dados)
        msg = mensagens["Cliente Teste"]
        self.assertEqual(msg.count("12.123.123/0001-01"), 2)

    def test_different_cnpjs_in_same_error(self):
        """CNPJs diferentes no mesmo erro → todos devem permanecer."""
        df = pd.DataFrame([
            {
                "Nome da Conta": "Cliente Teste",
                "Mensagem de Erro": "CNPJ não vinculado ao gov.br",
                "CNPJ": "11.111.111/0001-11",
                "Placa": "AAA1111",
            },
            {
                "Nome da Conta": "Cliente Teste",
                "Mensagem de Erro": "CNPJ não vinculado ao gov.br",
                "CNPJ": "22.222.222/0001-22",
                "Placa": "BBB2222",
            },
            {
                "Nome da Conta": "Cliente Teste",
                "Mensagem de Erro": "CNPJ não vinculado ao gov.br",
                "CNPJ": "33.333.333/0001-33",
                "Placa": "CCC3333",
            },
        ])

        dados, _ = process_dataframe(df)
        ocorrencias = dados["Cliente Teste"]["CNPJ não vinculado ao gov.br"]
        self.assertEqual(len(ocorrencias), 3)

        cnpjs_armazenados = [occ["cnpj"] for occ in ocorrencias]
        self.assertEqual(
            cnpjs_armazenados,
            ["11.111.111/0001-11", "22.222.222/0001-22", "33.333.333/0001-33"]
        )

        mensagens = build_messages(dados)
        msg = mensagens["Cliente Teste"]
        self.assertIn("11.111.111/0001-11", msg)
        self.assertIn("22.222.222/0001-22", msg)
        self.assertIn("33.333.333/0001-33", msg)

    def test_repeated_plates_and_renavams_in_same_error(self):
        """Placas/Renavams repetidos no mesmo erro → também devem ser deduplicados."""
        df_placa_renavam = pd.DataFrame([
            {
                "Nome da Conta": "Cliente Teste",
                "Mensagem de Erro": "Placa/Renavam não localizados",
                "Placa": "ABC-1234",
                "Renavam": "12345678901",
                "CNPJ": "11.111.111/0001-11",
            },
            {
                "Nome da Conta": "Cliente Teste",
                "Mensagem de Erro": "Placa/Renavam não localizados",
                "Placa": "ABC-1234",
                "Renavam": "12345678901",
                "CNPJ": "22.222.222/0001-22",
            },
            {
                "Nome da Conta": "Cliente Teste",
                "Mensagem de Erro": "Placa/Renavam não localizados",
                "Placa": "ABC-1234",
                "Renavam": "98765432100",
            },
        ])

        dados1, _ = process_dataframe(df_placa_renavam)
        ocorrencias1 = dados1["Cliente Teste"]["Renavam não localizados"]
        self.assertEqual(len(ocorrencias1), 2)
        
        msg1 = build_messages(dados1)["Cliente Teste"]
        self.assertEqual(msg1.count("ABC-1234 - 12345678901"), 1)
        self.assertEqual(msg1.count("ABC-1234 - 98765432100"), 1)

        df_apenas_placa = pd.DataFrame([
            {
                "Nome da Conta": "Cliente Teste",
                "Mensagem de Erro": "Veículo não encontrado",
                "Placa": "XYZ-9999",
                "Renavam": "11111111111",
            },
            {
                "Nome da Conta": "Cliente Teste",
                "Mensagem de Erro": "Veículo não encontrado",
                "Placa": "XYZ-9999",
                "Renavam": "22222222222",
            },
            {
                "Nome da Conta": "Cliente Teste",
                "Mensagem de Erro": "Veículo não encontrado",
                "Placa": "XYZ-9999",
                "Renavam": None,
            },
        ])

        dados2, _ = process_dataframe(df_apenas_placa)
        ocorrencias2 = dados2["Cliente Teste"]["Veículo não encontrado"]
        self.assertEqual(len(ocorrencias2), 1)

        msg2 = build_messages(dados2)["Cliente Teste"]
        self.assertEqual(msg2.count("XYZ-9999"), 1)

    def test_unique_indicators_behavior_unchanged(self):
        """Não alterar o comportamento de erros que já possuem indicadores únicos."""
        df = pd.DataFrame([
            {
                "Nome da Conta": "Cliente Teste",
                "Mensagem de Erro": "Veículo não encontrado",
                "Placa": "AAA1111",
            },
            {
                "Nome da Conta": "Cliente Teste",
                "Mensagem de Erro": "Veículo não encontrado",
                "Placa": "BBB2222",
            },
            {
                "Nome da Conta": "Cliente Teste",
                "Mensagem de Erro": "CNPJ não vinculado ao gov.br",
                "CNPJ": "12.123.123/0001-01",
            },
        ])

        dados, _ = process_dataframe(df)
        self.assertEqual(len(dados["Cliente Teste"]["Veículo não encontrado"]), 2)
        self.assertEqual(len(dados["Cliente Teste"]["CNPJ não vinculado ao gov.br"]), 1)

        msg = build_messages(dados)["Cliente Teste"]
        self.assertEqual(msg.count("AAA1111"), 1)
        self.assertEqual(msg.count("BBB2222"), 1)
        self.assertEqual(msg.count("12.123.123/0001-01"), 1)

    def test_message_builder_isolated_deduplication(self):
        """Garante que build_messages também deduplica se receber ocorrências duplicadas diretamente."""
        raw_processed = {
            "Cliente X": {
                "CNPJ não vinculado ao gov.br": [
                    {"cnpj": "12.123.123/0001-01"},
                    {"cnpj": "12.123.123/0001-01"},
                ],
                "Certificado Digital expirado. Por favor, utilize um novo": [
                    {"cnpj": "12.123.123/0001-01"},
                ],
            }
        }
        msgs = build_messages(raw_processed)
        msg = msgs["Cliente X"]
        self.assertEqual(msg.count("12.123.123/0001-01"), 2)


if __name__ == "__main__":
    unittest.main()
