import sqlite3
import unittest
from datetime import date, datetime
from pathlib import Path

import pandas as pd

# Redirecionar o banco para arquivo de teste temporário
TEST_DB_PATH = Path(__file__).resolve().parent / "test_client_history.db"
if TEST_DB_PATH.exists():
    try:
        TEST_DB_PATH.unlink()
    except Exception:
        pass

import core.db
core.db.get_db_path = lambda: TEST_DB_PATH

from core.db import get_connection, init_db, reset_client_history_db
from core.client_db import (
    get_all_history_clients,
    get_client_available_dates,
    get_client_consulta_details,
    get_client_consultas_history,
    get_client_error_ranking,
    get_client_evolution,
    get_client_summary,
    save_client_consultas,
)
from core.client_service import (
    extract_client_history_from_dataframe,
    find_data_consulta_column,
    parse_data_consulta,
    record_client_history,
)


class TestClientHistoryModule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    @classmethod
    def tearDownClass(cls):
        try:
            if TEST_DB_PATH.exists():
                TEST_DB_PATH.unlink()
        except Exception:
            pass

    def setUp(self):
        reset_client_history_db()

    def test_1_parse_data_consulta_formats(self):
        """Valida que datas nos mais variados formatos da planilha são convertidas para ISO sem alteração."""
        # Strings no padrão brasileiro
        self.assertEqual(parse_data_consulta("10/07/2026"), "2026-07-10")
        self.assertEqual(parse_data_consulta("10-07-2026"), "2026-07-10")
        self.assertEqual(parse_data_consulta("01/08/2026"), "2026-08-01")
        self.assertEqual(parse_data_consulta("10/07/2026 14:35:00"), "2026-07-10")

        # ISO
        self.assertEqual(parse_data_consulta("2026-07-10"), "2026-07-10")
        self.assertEqual(parse_data_consulta("2026-07-10T10:00:00"), "2026-07-10")

        # Objetos datetime / Timestamp
        self.assertEqual(parse_data_consulta(datetime(2026, 7, 10, 8, 30)), "2026-07-10")
        self.assertEqual(parse_data_consulta(date(2026, 7, 10)), "2026-07-10")
        self.assertEqual(parse_data_consulta(pd.Timestamp("2026-07-10")), "2026-07-10")

        # Valores nulos / inválidos não inferem data (retornam None)
        self.assertIsNone(parse_data_consulta(None))
        self.assertIsNone(parse_data_consulta(""))
        self.assertIsNone(parse_data_consulta("   "))
        self.assertIsNone(parse_data_consulta("nan"))
        self.assertIsNone(parse_data_consulta("data_invalida"))

    def test_2_find_data_consulta_column(self):
        """Identifica corretamente a coluna Data Consulta em DataFrames com variações de casing."""
        df1 = pd.DataFrame({"Data Consulta": ["10/07/2026"], "Nome da Conta": ["Cli A"]})
        self.assertEqual(find_data_consulta_column(df1), "Data Consulta")

        df2 = pd.DataFrame({"data consulta": ["10/07/2026"], "Nome da Conta": ["Cli A"]})
        self.assertEqual(find_data_consulta_column(df2), "data consulta")

        df3 = pd.DataFrame({"Data da Consulta": ["10/07/2026"], "Nome da Conta": ["Cli A"]})
        self.assertEqual(find_data_consulta_column(df3), "Data da Consulta")

    def test_3_extract_and_deduplicate_occurrences(self):
        """Garante que múltiplas linhas com o mesmo cliente e mesma Data Consulta não gerem duplicações desnecessárias."""
        df = pd.DataFrame([
            {
                "Data Consulta": "10/07/2026",
                "Nome da Conta": "Transportadora Coelho",
                "Mensagem de Erro": "CNPJ não vinculado ao gov.br",
                "CNPJ": "12.345.678/0001-90",
                "Placa": "ABC1111",
            },
            {
                "Data Consulta": "10/07/2026",
                "Nome da Conta": "Transportadora Coelho",
                "Mensagem de Erro": "CNPJ não vinculado ao gov.br",
                "CNPJ": "12.345.678/0001-90",
                "Placa": "ABC2222",
            },
            {
                "Data Consulta": "10/07/2026",
                "Nome da Conta": "Transportadora Coelho",
                "Mensagem de Erro": "Veículo não encontrado.",
                "Placa": "XYZ9999",
            },
            # Segunda consulta em outra data para o mesmo cliente
            {
                "Data Consulta": "17/07/2026",
                "Nome da Conta": "Transportadora Coelho",
                "Mensagem de Erro": "Veículo não encontrado.",
                "Placa": "XYZ8888",
            },
        ])

        consultas = extract_client_history_from_dataframe(df, file_hash="hash_teste_1")
        # Deve ter 2 consultas consolidadas (uma para 10/07/2026 e uma para 17/07/2026)
        self.assertEqual(len(consultas), 2)

        c1 = [c for c in consultas if c["data_consulta"] == "2026-07-10"][0]
        self.assertEqual(c1["cliente"], "Transportadora Coelho")
        self.assertEqual(c1["total_erros"], 3)
        self.assertEqual(c1["tipos_erros"], 2)

        # Verificar se os indicadores individuais foram coletados
        err_cnpj = [e for e in c1["erros"] if "CNPJ" in e["erro"]][0]
        self.assertEqual(err_cnpj["quantidade"], 2)
        self.assertIn("12.345.678/0001-90", err_cnpj["indicadores"])

    def test_4_save_client_consultas_and_idempotency(self):
        """Valida gravação atômica e prevenção de duplicidades no reprocessamento."""
        df = pd.DataFrame([
            {
                "Data Consulta": "10/07/2026",
                "Nome da Conta": "Transportadora Coelho",
                "Mensagem de Erro": "CNPJ não vinculado ao gov.br",
                "CNPJ": "12.345.678/0001-90",
                "Placa": "ABC1111",
            },
            {
                "Data Consulta": "24/07/2026",
                "Nome da Conta": "Transportadora Coelho",
                "Mensagem de Erro": "Veículo não encontrado.",
                "Placa": "ABC3333",
            },
        ])

        # 1ª gravação
        ok, msg, c_count = record_client_history(df, file_hash="hash_abc")
        self.assertTrue(ok)
        self.assertEqual(c_count, 2)

        # Reprocessamento da mesma planilha (mesmo hash) não duplica registros
        ok2, msg2, c_count2 = record_client_history(df, file_hash="hash_abc", force_replace=False)
        self.assertTrue(ok2)

        # Verificar no banco que existem exatamente 2 consultas
        clients = get_all_history_clients()
        self.assertEqual(clients, ["Transportadora Coelho"])

        summary = get_client_summary("Transportadora Coelho")
        self.assertEqual(summary["total_consultas"], 2)
        self.assertEqual(summary["total_erros"], 2)
        self.assertEqual(summary["primeira_consulta"], "10/07/2026")
        self.assertEqual(summary["ultima_consulta"], "24/07/2026")

    def test_5_client_consultas_views(self):
        """Valida as visualizações analíticas: ranking, evolução, histórico e detalhamento."""
        df = pd.DataFrame([
            # Rodada 1
            {
                "Data Consulta": "10/07/2026",
                "Nome da Conta": "Cliente Frota X",
                "Mensagem de Erro": "CNPJ não vinculado ao gov.br",
                "CNPJ": "11.111.111/0001-11",
                "Placa": "AAA1111",
            },
            {
                "Data Consulta": "10/07/2026",
                "Nome da Conta": "Cliente Frota X",
                "Mensagem de Erro": "CNPJ não vinculado ao gov.br",
                "CNPJ": "11.111.111/0001-11",
                "Placa": "AAA2222",
            },
            # Rodada 2
            {
                "Data Consulta": "17/07/2026",
                "Nome da Conta": "Cliente Frota X",
                "Mensagem de Erro": "Veículo não encontrado.",
                "Placa": "BBB3333",
            },
        ])

        record_client_history(df, file_hash="hash_view")

        # 1. Histórico de consultas
        history = get_client_consultas_history("Cliente Frota X")
        self.assertEqual(len(history), 2)
        # Ordem decrescente
        self.assertEqual(history[0]["data_consulta"], "17/07/2026")
        self.assertEqual(history[0]["total_erros"], 1)
        self.assertEqual(history[1]["data_consulta"], "10/07/2026")
        self.assertEqual(history[1]["total_erros"], 2)

        # 2. Ranking consolidado de erros
        ranking = get_client_error_ranking("Cliente Frota X")
        self.assertEqual(len(ranking), 2)
        # Erro mais frequente em 1º lugar
        self.assertIn("CNPJ não vinculado", ranking[0]["erro"])
        self.assertEqual(ranking[0]["total_ocorrencias"], 2)
        self.assertAlmostEqual(ranking[0]["percentual"], 66.67, places=1)

        # 3. Evolução temporal (ordem cronológica crescente)
        evolution = get_client_evolution("Cliente Frota X")
        self.assertEqual(len(evolution), 2)
        self.assertEqual(evolution[0]["data_consulta"], "10/07/2026")
        self.assertEqual(evolution[1]["data_consulta"], "17/07/2026")

        # 4. Detalhamento por data de consulta
        dates = get_client_available_dates("Cliente Frota X")
        self.assertEqual(dates, ["2026-07-17", "2026-07-10"])

        details_r1 = get_client_consulta_details("Cliente Frota X", "2026-07-10")
        self.assertEqual(len(details_r1), 1)
        self.assertIn("CNPJ não vinculado", details_r1[0]["erro"])
        self.assertEqual(details_r1[0]["quantidade"], 2)
        self.assertIn("11.111.111/0001-11", details_r1[0]["indicadores"])


if __name__ == "__main__":
    unittest.main()
