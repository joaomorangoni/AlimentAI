"""Validação e persistência dos endereços enviados pelos formulários públicos."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import validacao, solicitacao_service
from repositories import oferta_repository, solicitacao_repository

ENDERECO = dict(cidade="São Paulo", estado="sp", bairro="Centro", rua="Rua 25 de Março",
                numero="s/n", complemento="", cep="01001000")


class EnderecoTest(unittest.TestCase):
    def test_normaliza_sem_perder_numero_ou_regiao(self):
        resultado = validacao.localizacao({"endereco": ENDERECO})
        self.assertEqual(resultado["regiao"], "São Paulo")
        self.assertEqual(resultado["endereco"]["estado"], "SP")
        self.assertEqual(resultado["endereco"]["cep"], "01001-000")
        self.assertEqual(resultado["endereco"]["numero"], "s/n")
        self.assertIsNone(resultado["endereco"]["complemento"])

    def test_recusa_endereco_parcial_e_valores_invalidos(self):
        for campo in ENDERECO:
            if campo != "complemento":
                with self.subTest(campo=campo), self.assertRaises(ValueError):
                    validacao.localizacao({"endereco": {**ENDERECO, campo: ""}})
        for alteracao in ({"estado": "XX"}, {"cep": "123456789"}, {"numero": 12}, {"cidade": "<script>"}):
            with self.assertRaises(ValueError):
                validacao.localizacao({"endereco": {**ENDERECO, **alteracao}})

    def test_pedido_envia_endereco_validado_ao_repositorio(self):
        with mock.patch.object(solicitacao_repository, "criar_pendente") as criar:
            solicitacao_service.criar_pedido(dict(nome="ONG Teste", email="ong@exemplo.org",
                                                 endereco=ENDERECO, aceite=True))
        self.assertEqual(criar.call_args.args[0]["endereco"]["rua"], ENDERECO["rua"])

    def test_repositorios_inserem_endereco_na_mesma_transacao(self):
        dados = dict(nome="Teste", email="teste@exemplo.org", telefone=None, regiao="São Paulo",
                     mensagem=None, cnpj=None, capacidade_kg=None, alimento="Arroz", categoria="nao_perecivel",
                     quantidade_kg=10, validade="2026-12-01", endereco=ENDERECO)
        for repo in (oferta_repository, solicitacao_repository):
            cursor = mock.MagicMock()
            cursor.fetchone.side_effect = [(0,), (0,) if repo == oferta_repository else None, None, (1,)]
            with mock.patch.object(repo, "_transacao", side_effect=lambda fn: fn(cursor)):
                if repo == oferta_repository:
                    repo.criar(dados, "hash", 100, 3)
                else:
                    repo.criar_pendente(dados, 100)
            sql, params = cursor.execute.call_args.args
            self.assertIn("endereco", sql)
            self.assertEqual(params[-1].obj, ENDERECO)
