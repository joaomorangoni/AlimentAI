"""Migracoes: ordem, seguranca (so aditivas e idempotentes) e aplicacao automatica ao iniciar o servidor. Sem banco."""
import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("API_TOKEN", "t" * 40)

import migrar  # noqa: E402
import server  # noqa: E402


def sem_comentarios(sql):
    return "\n".join(linha for linha in sql.splitlines() if not linha.strip().startswith("--"))


class ArquivosTest(unittest.TestCase):
    def test_esquema_primeiro_e_migracoes_em_ordem(self):
        nomes = [a.name for a in migrar.arquivos()]
        self.assertEqual(nomes[0], "schema.sql")
        self.assertEqual(nomes[1:], sorted(nomes[1:]))
        self.assertEqual([n[:3] for n in nomes[1:]], [f"{i:03d}" for i in range(1, len(nomes))])  # sem buracos na numeracao

    def test_so_aditivas_e_idempotentes(self):
        for arquivo in migrar.arquivos():
            sql = sem_comentarios(arquivo.read_text(encoding="utf-8"))
            self.assertIsNone(re.search(r"\bDROP\b|\bTRUNCATE\b|\bDELETE\s+FROM\b|\bUPDATE\s+\w+\s+SET\b", sql, re.I), arquivo.name)
            self.assertIsNone(re.search(r"ALTER\s+TABLE\s+\w+\s+(DROP|RENAME|ALTER\s+COLUMN)", sql, re.I), arquivo.name)
            for criacao in re.findall(r"CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX)\s+(?!IF NOT EXISTS)", sql, re.I):
                self.fail(f"{arquivo.name}: CREATE sem IF NOT EXISTS ({criacao!r})")
            for coluna in re.findall(r"ADD\s+COLUMN\s+(?!IF NOT EXISTS)", sql, re.I):
                self.fail(f"{arquivo.name}: ADD COLUMN sem IF NOT EXISTS ({coluna!r})")


class AplicarTest(unittest.TestCase):
    class Conexao:
        def __init__(self):
            self.executados, self.commits, self.rollbacks, self.fechada = [], 0, 0, False

        def cursor(self):
            conexao = self

            class Cursor:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def execute(self, sql):
                    conexao.executados.append(sql)

            return Cursor()

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.fechada = True

    def test_aplica_cada_arquivo_em_sua_transacao(self):
        conexao = self.Conexao()
        nomes = migrar.aplicar(conexao)
        self.assertEqual(nomes, [a.name for a in migrar.arquivos()])
        self.assertEqual((len(conexao.executados), conexao.commits, conexao.rollbacks), (len(nomes), len(nomes), 0))
        self.assertFalse(conexao.fechada)  # a conexao recebida de fora e de quem a abriu

    def test_erro_desfaz_e_propaga(self):
        conexao = self.Conexao()
        conexao.cursor = mock.Mock(side_effect=RuntimeError("sem permissao"))
        with self.assertRaises(RuntimeError):
            migrar.aplicar(conexao)
        self.assertEqual(conexao.rollbacks, 1)

    def test_conexao_propria_e_fechada(self):
        conexao = self.Conexao()
        with mock.patch.object(migrar, "conectar", return_value=conexao):
            migrar.aplicar()
        self.assertTrue(conexao.fechada)


class MigracaoAoIniciarTest(unittest.TestCase):
    def test_aplica_por_padrao(self):
        with mock.patch.dict(os.environ, {"AUTO_MIGRAR": "1"}), mock.patch.object(migrar, "aplicar", return_value=["a.sql"]) as aplica:
            server.migrar_banco()
        aplica.assert_called_once_with()

    def test_pode_ser_desligada(self):
        with mock.patch.dict(os.environ, {"AUTO_MIGRAR": "0"}), mock.patch.object(migrar, "aplicar") as aplica:
            server.migrar_banco()
        aplica.assert_not_called()

    def test_banco_fora_do_ar_nao_derruba_o_servidor(self):
        with mock.patch.dict(os.environ, {"AUTO_MIGRAR": "1"}), \
                mock.patch.object(migrar, "aplicar", side_effect=OSError("banco fora do ar")), \
                self.assertLogs(level="ERROR"):
            server.migrar_banco()  # nao levanta


if __name__ == "__main__":
    unittest.main()
