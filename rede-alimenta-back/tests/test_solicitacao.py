"""Pedido de acesso ao portal feito por ONGs: validacao, resposta uniforme e rotas do administrador. Sem banco."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["API_TOKEN"] = "t" * 40

from repositories import solicitacao_repository  # noqa: E402
from services import ong_service, solicitacao_service  # noqa: E402

PEDIDO = {"nome": "ONG Esperança", "email": "Contato@Esperanca.org", "telefone": "(11) 91234-5678",
          "regiao": "São Paulo", "mensagem": "Queremos receber doações.", "aceite": True, "site": ""}


class PedidoAcessoTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(solicitacao_service.solicitacao_repository, "criar_pendente", return_value=True)
        self.grava = patcher.start()
        self.addCleanup(patcher.stop)

    def test_pedido_valido_grava_dados_limpos(self):
        resposta = solicitacao_service.criar_pedido(PEDIDO)
        self.assertEqual(set(resposta), {"mensagem"})
        pedido, limite = self.grava.call_args.args
        self.assertEqual(pedido["email"], "contato@esperanca.org")
        self.assertEqual(limite, solicitacao_service.MAXIMO_PENDENTES)

    def test_resposta_e_a_mesma_com_pedido_repetido(self):
        primeira = solicitacao_service.criar_pedido(PEDIDO)
        self.grava.return_value = False
        self.assertEqual(solicitacao_service.criar_pedido(PEDIDO), primeira)

    def test_campo_armadilha_descarta_em_silencio(self):
        self.assertIn("mensagem", solicitacao_service.criar_pedido({**PEDIDO, "site": "http://spam.example"}))
        self.grava.assert_not_called()

    def test_dados_invalidos_sao_recusados(self):
        for campos in ({"aceite": False}, {"aceite": "true"}, {"nome": "<b>x</b>"}, {"email": "a@b"}, {"regiao": "1"},
                       {"telefone": "123"}, {"mensagem": "x" * 501}, {"mensagem": 5}):
            with self.assertRaises(ValueError, msg=campos):
                solicitacao_service.criar_pedido({**PEDIDO, **campos})
        for dados in ({**PEDIDO, "status": "atendida"}, {**PEDIDO, "ong_id": 1}, [], None):
            with self.assertRaises(ValueError):
                solicitacao_service.criar_pedido(dados)
        self.grava.assert_not_called()

    def test_mensagem_e_telefone_sao_opcionais(self):
        solicitacao_service.criar_pedido({**PEDIDO, "mensagem": "  ", "telefone": None})
        self.assertIsNone(self.grava.call_args.args[0]["mensagem"])

    def test_cnpj_e_capacidade_opcionais_validos(self):
        solicitacao_service.criar_pedido({**PEDIDO, "cnpj": "11.222.333/0001-81", "capacidade_kg": 50})
        pedido = self.grava.call_args.args[0]
        self.assertEqual((pedido["cnpj"], pedido["capacidade_kg"]), ("11222333000181", 50.0))
        solicitacao_service.criar_pedido({**PEDIDO, "cnpj": "", "capacidade_kg": None})
        pedido = self.grava.call_args.args[0]
        self.assertEqual((pedido["cnpj"], pedido["capacidade_kg"]), (None, None))

    def test_cnpj_e_capacidade_invalidos_sao_recusados(self):
        for campos in ({"cnpj": "11.222.333/0001-82"}, {"cnpj": "11111111111111"}, {"cnpj": "123"}, {"cnpj": "abcdefghijklmn"},
                       {"cnpj": 11222333000181}, {"capacidade_kg": 0}, {"capacidade_kg": -5}, {"capacidade_kg": "50"},
                       {"capacidade_kg": 99999999}):
            with self.assertRaises(ValueError, msg=campos):
                solicitacao_service.criar_pedido({**PEDIDO, **campos})
        self.grava.assert_not_called()

    def test_encerrar_valida_id_e_estado(self):
        with mock.patch.object(solicitacao_service.solicitacao_repository, "encerrar", return_value=False):
            with self.assertRaises(ValueError):
                solicitacao_service.encerrar(3, True)
        for ruim in (0, -1, "1", True, None):
            with self.assertRaises(ValueError):
                solicitacao_service.encerrar(ruim, True)


class PrivacidadeDoPedidoTest(unittest.TestCase):
    """Descartar um pedido apaga os dados pessoais; atender apenas muda a situacao (a ONG passa a existir no cadastro)."""

    def executa(self, novo_status):
        comandos = []

        class Cursor:
            rowcount = 1

            def execute(self, sql, parametros=None):
                comandos.append(" ".join(sql.split()))

        with mock.patch.object(solicitacao_repository, "_transacao", side_effect=lambda f: f(Cursor())):
            self.assertTrue(solicitacao_repository.encerrar(7, novo_status))
        return comandos[0]

    def test_descartar_apaga_dados_pessoais(self):
        sql = self.executa("descartada")
        for campo in ("nome = '(removido)'", "telefone = NULL", "mensagem = NULL", "cnpj = NULL", "email = 'removido-'"):
            self.assertIn(campo, sql)
        self.assertIn("status = 'pendente'", sql)  # so atua em pedido pendente

    def test_atender_nao_mexe_nos_dados(self):
        sql = self.executa("atendida")
        self.assertNotIn("removido", sql)
        self.assertNotIn("NULL", sql)


class CnpjNaOngTest(unittest.TestCase):
    def test_criar_ong_valida_e_normaliza_o_cnpj(self):
        with mock.patch.object(ong_service, "cadastrar_ong", return_value=1) as grava:
            ong_service.criar_ong("ONG Boa", "o@boa.org", None, "Santos", 40, cnpj="11.222.333/0001-81")
            self.assertEqual(grava.call_args.args[-1], "11222333000181")
            ong_service.criar_ong("ONG Boa", "o@boa.org", None, "Santos", 40)
            self.assertIsNone(grava.call_args.args[-1])
            with self.assertRaises(ValueError):
                ong_service.criar_ong("ONG Boa", "o@boa.org", None, "Santos", 40, cnpj="11.222.333/0001-82")

    def test_editar_so_mexe_no_cnpj_quando_ele_e_enviado(self):
        with mock.patch.object(ong_service, "obter_ong"), mock.patch.object(ong_service, "atualizar_ong") as atualiza:
            ong_service.editar_ong(1, "ONG Boa", None, "Santos", 40)
            self.assertEqual(atualiza.call_args.args[5:], (False, None))
            ong_service.editar_ong(1, "ONG Boa", None, "Santos", 40, cnpj="11222333000181")
            self.assertEqual(atualiza.call_args.args[5:], (True, "11222333000181"))
            ong_service.editar_ong(1, "ONG Boa", None, "Santos", 40, cnpj=None)
            self.assertEqual(atualiza.call_args.args[5:], (True, None))


if __name__ == "__main__":
    unittest.main()
