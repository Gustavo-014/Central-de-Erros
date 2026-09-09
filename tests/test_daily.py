import hashlib
import os
import sqlite3
import unittest
from pathlib import Path
import pandas as pd

# Configurar banco de testes temporário
TEST_DB_PATH = Path(__file__).resolve().parent / "test_history.db"
if TEST_DB_PATH.exists():
    try:
        TEST_DB_PATH.unlink()
    except Exception:
        pass

# Apontar get_db_path para TEST_DB_PATH
import core.db
core.db.get_db_path = lambda: TEST_DB_PATH

from core.db import get_connection, init_db, reset_daily_db, save_client_contact, register_sent_message
from core.error_classifier import classify_error
from core.daily_db import (
    delete_snapshot_by_date,
    get_available_dates,
    get_client_ranking,
    get_client_errors,
    get_client_evolution,
    get_comparison_data,
    get_period_data,
    get_snapshot_by_date,
    get_snapshots_evolution,
    get_top_errors,
    get_recurrent_errors,
)
from core.daily_service import (
    compute_file_hash,
    extract_date_from_filename,
    get_daily_answers_single,
    get_daily_answers_comparison,
    get_daily_answers_period,
    record_daily_snapshot,
)


class TestDailyModule(unittest.TestCase):
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
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM daily_erros;")
            cursor.execute("DELETE FROM daily_clientes;")
            cursor.execute("DELETE FROM daily_snapshots;")
            conn.commit()

    def test_1_create_and_reset_daily_db(self):
        """1. Valida criação/recriação da base e que reset_daily_db preserva contatos e histórico de envios."""
        # Inserir contato e mensagem enviada da aba operacional
        save_client_contact("Cliente Operacional", "Grupo Suporte", "group_name")
        register_sent_message("Cliente Operacional", "Erro X")

        # Inserir snapshot
        dados = {"Cliente Operacional": {"Veículo não encontrado.": [{"placa": "A1"}]}}
        record_daily_snapshot(dados, filename="test.xlsx", target_date="2026-09-01")

        # Executar reset_daily_db
        reset_daily_db()

        # Verificar que daily_* foi resetado mas contatos e histórico foram preservados
        dates = get_available_dates()
        self.assertEqual(len(dates), 0)

        with get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT count(*) FROM client_contacts WHERE client_name = 'Cliente Operacional'")
            self.assertEqual(c.fetchone()[0], 1)
            c.execute("SELECT count(*) FROM sent_history WHERE client_name = 'Cliente Operacional'")
            self.assertEqual(c.fetchone()[0], 1)

    def test_2_record_snapshots_by_date(self):
        """2. Gravação de snapshots com a data correta de incidência da planilha."""
        dados = {"Cliente Alfa": {"Veículo não encontrado.": [{"placa": "ABC1234"}]}}
        ok, msg = record_daily_snapshot(dados, filename="erros-01-09.xlsx", target_date="2026-09-01")
        self.assertTrue(ok)

        snap = get_snapshot_by_date("2026-09-01")
        self.assertIsNotNone(snap)
        self.assertEqual(snap["data"], "2026-09-01")
        self.assertEqual(snap["total_erros"], 1)

    def test_3_deduplication_by_hash(self):
        """3. Deduplicação por hash: se a mesma planilha for reenviada no mesmo dia, não duplica."""
        dados = {"Cliente Alfa": {"Veículo não encontrado.": [{"placa": "ABC1234"}]}}
        file_bytes = b"conteudo_arquivo_hash_1"
        ok1, msg1 = record_daily_snapshot(dados, filename="erros.xlsx", file_bytes=file_bytes, target_date="2026-09-01")
        self.assertTrue(ok1)

        ok2, msg2 = record_daily_snapshot(dados, filename="erros_copia.xlsx", file_bytes=file_bytes, target_date="2026-09-01")
        self.assertTrue(ok2)
        self.assertIn("mesmo conteúdo já registrado", msg2)

        dates = get_available_dates()
        self.assertEqual(len(dates), 1)

    def test_4_replace_snapshot_on_same_date_new_hash(self):
        """4. Exige confirmação para substituir snapshot com hash diferente; substitui atomicamente se force_replace=True."""
        dados_v1 = {"Cliente Alfa": {"Veículo não encontrado.": [{"placa": "ABC1234"}, {"placa": "DEF5678"}]}}
        ok1, msg1 = record_daily_snapshot(dados_v1, filename="v1.xlsx", file_bytes=b"hash_v1", target_date="2026-09-01")
        self.assertTrue(ok1)

        dados_v2 = {"Cliente Alfa": {"Veículo não encontrado.": [{"placa": "ABC1234"}]}}
        # Sem confirmação (force_replace=False) -> bloqueia e avisa EXISTS
        ok2, msg2 = record_daily_snapshot(dados_v2, filename="v2.xlsx", file_bytes=b"hash_v2", target_date="2026-09-01", force_replace=False)
        self.assertFalse(ok2)
        self.assertEqual(msg2, "EXISTS")

        # Snapshot original continua inalterado (2 erros)
        snap_intacto = get_snapshot_by_date("2026-09-01")
        self.assertEqual(snap_intacto["total_erros"], 2)

        # Com confirmação explícita (force_replace=True) -> substitui com sucesso
        ok3, msg3 = record_daily_snapshot(dados_v2, filename="v2.xlsx", file_bytes=b"hash_v2", target_date="2026-09-01", force_replace=True)
        self.assertTrue(ok3)

        snap = get_snapshot_by_date("2026-09-01")
        self.assertEqual(snap["total_erros"], 1)
        self.assertEqual(len(get_available_dates()), 1)

    def test_13_delete_snapshot_by_date(self):
        """13. Exclusão de snapshot por data através de delete_snapshot_by_date mantendo dados operacionais."""
        dados = {"Cliente Alfa": {"Veículo não encontrado.": [{"placa": "ABC1234"}]}}
        record_daily_snapshot(dados, filename="teste_del.xlsx", target_date="2026-09-05")
        snap = get_snapshot_by_date("2026-09-05")
        self.assertIsNotNone(snap)

        ok_del, msg_del = delete_snapshot_by_date("2026-09-05")
        self.assertTrue(ok_del)
        self.assertIsNone(get_snapshot_by_date("2026-09-05"))

        # Tentativa de excluir data inexistente
        ok_del2, msg_del2 = delete_snapshot_by_date("2026-09-05")
        self.assertFalse(ok_del2)

    def test_5_and_8_single_day_query_no_automatic_yesterday(self):
        """5 e 8. Consulta de um único dia sem comparação automática com o último snapshot anterior."""
        dados_d1 = {"Cliente Alfa": {"Veículo não encontrado.": [{"placa": "A1"}]}}
        record_daily_snapshot(dados_d1, filename="d1.xlsx", file_bytes=b"d1", target_date="2026-09-01")

        dados_d2 = {"Cliente Alfa": {"Veículo não encontrado.": [{"placa": "A1"}, {"placa": "A2"}]}}
        record_daily_snapshot(dados_d2, filename="d2.xlsx", file_bytes=b"d2", target_date="2026-09-02")

        # Ao consultar o dia 2 no modo single, o resumo não deve conter deltas ou 'vs ontem'
        answers_d2 = get_daily_answers_single("2026-09-02")
        self.assertEqual(answers_d2["mode"], "single")
        self.assertEqual(answers_d2["total_erros"], 2)
        self.assertNotIn("delta_abs", answers_d2)
        self.assertNotIn("delta_pct", answers_d2)
        self.assertNotIn("has_previous", answers_d2)

    def test_6_and_9_and_10_comparison_explicit_dates_and_deltas(self):
        """6, 9 e 10. Comparação explícita entre duas datas selecionadas pelo usuário e cálculo de deltas."""
        dados_d1 = {
            "Cliente Alfa": {"Veículo não encontrado.": [{"placa": "A1"}]},
            "Cliente Beta": {"Usuário ou senha inválidos": [{"placa": "B1"}, {"placa": "B2"}]},
        }
        record_daily_snapshot(dados_d1, filename="d1.xlsx", file_bytes=b"d1", target_date="2026-09-01")

        dados_d2 = {
            "Cliente Alfa": {"Veículo não encontrado.": [{"placa": "A1"}, {"placa": "A2"}, {"placa": "A3"}]},
            "Cliente Beta": {"Usuário ou senha inválidos": [{"placa": "B1"}]},
        }
        record_daily_snapshot(dados_d2, filename="d2.xlsx", file_bytes=b"d2", target_date="2026-09-08")

        # Comparar 01/09 e 08/09
        comp = get_comparison_data("2026-09-01", "2026-09-08")
        self.assertNotIn("error", comp)
        self.assertEqual(comp["date_start"], "2026-09-01")
        self.assertEqual(comp["date_end"], "2026-09-08")

        # Métricas globais:
        # 01/09: 3 erros (1 consulta, 2 usuário). 08/09: 4 erros (3 consulta, 1 usuário).
        # Delta = 4 - 3 = +1 (+33.33%)
        tot = comp["metrics"]["total_erros"]
        self.assertEqual(tot["start"], 3)
        self.assertEqual(tot["end"], 4)
        self.assertEqual(tot["delta_abs"], 1)
        self.assertAlmostEqual(tot["delta_pct"], 33.33, places=1)

        # Delta por cliente:
        # Cliente Alfa: 1 -> 3 (delta = +2)
        # Cliente Beta: 2 -> 1 (delta = -1)
        cli_vars = {c["cliente"]: c for c in comp["client_variations"]}
        self.assertEqual(cli_vars["Cliente Alfa"]["delta_abs"], 2)
        self.assertEqual(cli_vars["Cliente Beta"]["delta_abs"], -1)

        # Risers deve ter Cliente Alfa no topo
        self.assertEqual(comp["risers"][0]["cliente"], "Cliente Alfa")
        # Fallers deve ter Cliente Beta no topo
        self.assertEqual(comp["fallers"][0]["cliente"], "Cliente Beta")

        # Validação de mesma data proibida (Ajuste 4)
        same_cmp = get_comparison_data("2026-09-01", "2026-09-01")
        self.assertIn("error", same_cmp)

    def test_7_and_11_period_evolution_and_gaps_and_unique_clients(self):
        """7 e 11. Análise de período com dias sem snapshot (gaps) e Total Clientes Únicos (Ajuste 2)."""
        # Snapshots em 01/09, 02/09 e 05/09 (gap nos dias 03 e 04)
        dados_d1 = {"Cliente A": {"Veículo não encontrado.": [{"placa": "P1"}]}}
        dados_d2 = {
            "Cliente A": {"Veículo não encontrado.": [{"placa": "P1"}]},
            "Cliente B": {"Usuário ou senha inválidos": [{"placa": "P2"}]},
        }
        dados_d5 = {
            "Cliente A": {"Veículo não encontrado.": [{"placa": "P1"}]},
            "Cliente C": {"Veículo não encontrado.": [{"placa": "P3"}]},
        }
        record_daily_snapshot(dados_d1, filename="d1.xlsx", file_bytes=b"d1", target_date="2026-09-01")
        record_daily_snapshot(dados_d2, filename="d2.xlsx", file_bytes=b"d2", target_date="2026-09-02")
        record_daily_snapshot(dados_d5, filename="d5.xlsx", file_bytes=b"d5", target_date="2026-09-05")

        period = get_period_data("2026-09-01", "2026-09-05")
        self.assertEqual(period["dias_com_snapshot"], 3)
        # Não foram inventados dias para 03 e 04
        datas_presentes = [s["data"] for s in period["snapshots"]]
        self.assertEqual(datas_presentes, ["2026-09-01", "2026-09-02", "2026-09-05"])

        # AJUSTE 2: Total Clientes Únicos = COUNT(DISTINCT cliente)
        # Cliente A (aparece em 3 dias), Cliente B (1 dia), Cliente C (1 dia) -> Total único = 3!
        self.assertEqual(period["total_clientes_unicos"], 3)

        # Volume acumulado = 1 + 2 + 2 = 5 erros
        self.assertEqual(period["total_erros_periodo"], 5)
        # Média diária nos dias ativos = 5 / 3 = 1.666
        self.assertAlmostEqual(period["media_diaria_erros"], 1.6666, places=2)

    def test_12_classification_with_raw_row_by_client_and_error(self):
        """12 e 18. Classificação associada rigorosamente à ocorrência do par (cliente, erro)."""
        df_mock = pd.DataFrame(
            [
                {
                    "Nome da Conta": "Cliente A",
                    "Mensagem de Erro": "Erro desconhecido customizado 1",
                    "tipo": "Erro de Consulta",
                    "Placa": "AAA1111",
                },
                {
                    "Nome da Conta": "Cliente B",
                    "Mensagem de Erro": "Erro desconhecido customizado 2",
                    "tipo": "Erro de Usuário",
                    "Placa": "BBB2222",
                },
            ]
        )
        dados = {
            "Cliente A": {"Erro desconhecido customizado 1": [{"placa": "AAA1111"}]},
            "Cliente B": {"Erro desconhecido customizado 2": [{"placa": "BBB2222"}]},
        }
        ok, _ = record_daily_snapshot(
            dados=dados,
            dataframe=df_mock,
            filename="teste_classif.xlsx",
            target_date="2026-09-08",
        )
        self.assertTrue(ok)

        snap = get_snapshot_by_date("2026-09-08")
        self.assertEqual(snap["erros_consulta"], 1)
        self.assertEqual(snap["erros_usuario"], 1)
        self.assertEqual(snap["erros_nao_classificados"], 0)

        # Verificar no detalhamento por cliente
        errs_a = get_client_errors(snap["id"], "Cliente A")
        self.assertEqual(errs_a[0]["tipo"], "consulta")

        errs_b = get_client_errors(snap["id"], "Cliente B")
        self.assertEqual(errs_b[0]["tipo"], "usuario")

    def test_extract_date_from_filename(self):
        """Validação da extração de datas em nomes de arquivos."""
        self.assertEqual(extract_date_from_filename("erros-28/08.xlsx", default_year=2026), "2026-08-28")
        self.assertEqual(extract_date_from_filename("erros-29/08.xlsx", default_year=2026), "2026-08-29")
        self.assertEqual(extract_date_from_filename("erros-28-08.xlsx", default_year=2026), "2026-08-28")
        self.assertEqual(extract_date_from_filename("erros_29_08.xlsx", default_year=2026), "2026-08-29")
        self.assertEqual(extract_date_from_filename("erros_28.08.2026.xlsx"), "2026-08-28")
        self.assertEqual(extract_date_from_filename("erros_2026-08-29.xlsx"), "2026-08-29")
        self.assertIsNone(extract_date_from_filename("planilha_aleatoria.xlsx"))


if __name__ == "__main__":
    unittest.main()
