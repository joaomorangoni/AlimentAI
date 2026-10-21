"""Fluxo novo: oferta publica pendente, aprovacao do gestor, portal da ONG por link e sincronizacao de status. Sem banco."""
import http.client
import json
import os
import sys
import threading
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TOKEN = "t" * 40
os.environ["API_TOKEN"] = TOKEN

import security  # noqa: E402
import server  # noqa: E402
from ia import validador_alimento  # noqa: E402
from services import doacao_service, match_service, oferta_service, ong_portal_service, publico_service, validacao  # noqa: E402


def em(dias):
    return (validacao.hoje() + timedelta(days=dias)).isoformat()


OFERTA = {
    "nome": "Maria da Silva", "email": "Maria@Exemplo.com", "telefone": "(11) 91234-5678", "regiao": "São Paulo",
    "alimento": "tomate", "categoria": "hortifruti", "quantidade_kg": 12, "validade": em(5), "aceite": True, "site": "",
}


class SemIA(unittest.TestCase):
    def setUp(self):
        validador_alimento._cache.clear()
        ambiente = mock.patch.dict(os.environ, {"LLM_BASE_URL": "", "LLM2_BASE_URL": "", "ALIMENTO_FALHA_ABERTA": ""})
        ambiente.start()
        self.addCleanup(ambiente.stop)


class LinkOngTest(unittest.TestCase):
    def test_codigo_e_deterministico_e_unico_por_ong_e_versao(self):
        a = security.codigo_link_ong(1, 1)
        self.assertEqual(a, security.codigo_link_ong(1, 1))
        self.assertNotEqual(a, security.codigo_link_ong(2, 1))
        self.assertNotEqual(a, security.codigo_link_ong(1, 2))
        self.assertGreaterEqual(len(a), 26)

    def test_validacao_do_codigo(self):
        codigo = security.codigo_link_ong(3, 1)
        self.assertTrue(security.codigo_link_valido(codigo, 3, 1))
        for ruim in ("", None, "x", codigo[:-1], codigo + "a", codigo.upper()):
            self.assertFalse(security.codigo_link_valido(ruim, 3, 1), ruim)
        self.assertFalse(security.codigo_link_valido(codigo, 4, 1))
        self.assertFalse(security.codigo_link_valido(codigo, 3, 2))

    def test_segredo_nao_e_o_proprio_token_e_pode_ser_definido(self):
        self.assertNotEqual(security.segredo_links_ong(), TOKEN.encode())
        antes = security.codigo_link_ong(1, 1)
        with mock.patch.dict(os.environ, {"ONG_LINK_SECRET": "s" * 40}):
            self.assertNotEqual(antes, security.codigo_link_ong(1, 1))


class OfertaPublicaTest(SemIA):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(publico_service.oferta_repository, "criar", return_value=1)
        self.grava = patcher.start()
        self.addCleanup(patcher.stop)

    def oferta(self, **campos):
        return publico_service.criar_oferta({**OFERTA, **campos})

    def test_oferta_valida_fica_em_ofertas_publicas_com_dados_limpos(self):
        resposta = self.oferta(nome="  Maria   da Silva ")
        self.assertEqual(set(resposta), {"mensagem", "codigo"})
        oferta, codigo_hash, limite, por_email = self.grava.call_args.args
        self.assertEqual((oferta["nome"], oferta["email"], oferta["telefone"], oferta["regiao"]),
                         ("Maria da Silva", "maria@exemplo.com", "(11) 91234-5678", "São Paulo"))
        self.assertEqual((oferta["alimento"], oferta["categoria"], oferta["quantidade_kg"]), ("tomate", "hortifruti", 12.0))
        self.assertEqual((limite, por_email), (doacao_service.MAXIMO_PENDENTES, publico_service.MAXIMO_PENDENTES_POR_EMAIL))
        # O banco guarda so o hash do codigo; o codigo em si vai apenas para quem enviou.
        self.assertEqual(codigo_hash, publico_service.hash_codigo(resposta["codigo"]))
        self.assertNotIn(resposta["codigo"], codigo_hash)
        self.assertGreaterEqual(len(resposta["codigo"]), 22)

    def test_oferta_nao_cria_doador_nem_doacao(self):
        with mock.patch.object(publico_service.fluxo_repository, "cadastrar_oferta_publica") as legado:
            self.oferta()
        legado.assert_not_called()

    def test_banco_sem_a_migracao_cai_no_fluxo_antigo_sem_codigo(self):
        self.grava.side_effect = psycopg.errors.UndefinedTable("ofertas_publicas")
        with mock.patch.object(publico_service.fluxo_repository, "cadastrar_oferta_publica", return_value=1) as legado:
            resposta = self.oferta()
        self.assertEqual(set(resposta), {"mensagem"})
        doador, doacao, limite = legado.call_args.args
        self.assertEqual(doador["email"], "maria@exemplo.com")
        self.assertEqual(doacao["alimento"], "tomate")
        self.assertEqual(limite, doacao_service.MAXIMO_PENDENTES)

    def test_campo_armadilha_descarta_em_silencio_com_resposta_igual_a_de_sucesso(self):
        resposta = self.oferta(site="http://spam.example")
        self.assertEqual(set(resposta), {"mensagem", "codigo"})  # o robo nao distingue; o codigo nao existe no banco
        self.grava.assert_not_called()

    def test_aceite_e_obrigatorio(self):
        for aceite in (False, None, "true", 1, "sim"):
            with self.assertRaises(ValueError):
                self.oferta(aceite=aceite)

    def test_campos_desconhecidos_e_formato(self):
        for dados in ({**OFERTA, "status": "disponivel"}, {**OFERTA, "doador_id": 1}, [], "x", None):
            with self.assertRaises(ValueError):
                publico_service.criar_oferta(dados)
        self.grava.assert_not_called()

    def test_dados_estranhos_sao_recusados(self):
        for campos in ({"nome": "<b>x</b>"}, {"email": "a@b"}, {"telefone": "123"}, {"regiao": "1"}, {"alimento": "cachorro"},
                       {"alimento": "tomate", "categoria": "carnes"}, {"quantidade_kg": 0}, {"quantidade_kg": 99999},
                       {"validade": em(-1)}, {"validade": em(400)}, {"validade": "31/12/2026"}, {"categoria": "abc"}):
            with self.assertRaises(ValueError, msg=campos):
                self.oferta(**campos)
        self.grava.assert_not_called()

    def test_sem_confirmacao_da_ia_nao_grava(self):
        with self.assertRaises(doacao_service.ValidacaoIndisponivel):
            self.oferta(alimento="zorblax")
        self.grava.assert_not_called()


class OfertaDoGestorTest(unittest.TestCase):
    """Aprovar cria doador e doacao disponivel (no repositorio, em uma transacao); recusar apaga os dados pessoais."""

    def test_aprovar_e_recusar_validam_o_id_e_chamam_o_repositorio(self):
        with mock.patch.object(oferta_service.oferta_repository, "aprovar", return_value=7) as aprova, \
                mock.patch.object(oferta_service.oferta_repository, "recusar", return_value=True) as recusa:
            self.assertEqual(oferta_service.aprovar(3), 7)
            self.assertEqual(aprova.call_args.args, (3, validacao.hoje()))
            oferta_service.recusar(3)
            recusa.assert_called_once_with(3)
            for ruim in (0, -1, "1", True, None, 10 ** 30):
                for funcao in (oferta_service.aprovar, oferta_service.recusar):
                    with self.assertRaises(ValueError, msg=ruim):
                        funcao(ruim)

    def test_recusar_oferta_que_ja_foi_decidida_e_erro(self):
        with mock.patch.object(oferta_service.oferta_repository, "recusar", return_value=False):
            with self.assertRaisesRegex(ValueError, "pendente"):
                oferta_service.recusar(3)

    def test_listar_formata_e_nao_quebra_sem_a_migracao(self):
        linha = (4, "Maria", "m@x.com", None, "Santos", "tomate", "hortifruti", Decimal("12.50"), date(2026, 10, 20), None)
        with mock.patch.object(oferta_service.oferta_repository, "listar_pendentes", return_value=[linha]):
            lista = oferta_service.listar()
        self.assertEqual((lista[0]["id"], lista[0]["alimento"], lista[0]["quantidade_kg"]), (4, "tomate", 12.5))
        with mock.patch.object(oferta_service.oferta_repository, "listar_pendentes",
                               side_effect=psycopg.errors.UndefinedTable("ofertas_publicas")):
            self.assertEqual(oferta_service.listar(), [])


class AcompanhamentoDaOfertaTest(unittest.TestCase):
    CODIGO = "A" * 22

    def estado(self, status_oferta, status_doacao=None, status_match=None, ong=None):
        linha = (status_oferta, "Tomate", Decimal("12"), datetime(2026, 10, 14, 9, 0), status_doacao, status_match, ong)
        with mock.patch.object(publico_service.oferta_repository, "acompanhar", return_value=linha) as consulta:
            resposta = publico_service.acompanhar(self.CODIGO)
        consulta.assert_called_once_with(publico_service.hash_codigo(self.CODIGO))  # so o hash chega ao banco
        return resposta

    def test_etapas_vistas_pelo_doador(self):
        casos = [
            (("pendente",), "analise", 1, False),
            (("recusada",), "recusada", 1, True),
            (("aprovada", "disponivel"), "procurando_ong", 2, False),
            (("aprovada", "reservada", "pendente"), "ong_indicada", 3, False),
            (("aprovada", "reservada", "aceito", "ONG Boa"), "ong_aceitou", 3, False),
            (("aprovada", "concluida", "concluido", "ONG Boa"), "entregue", 4, True),
            (("aprovada", "cancelada"), "encerrada", 2, True),
            (("aprovada", None), "encerrada", 2, True),
        ]
        for argumentos, etapa, passo, final in casos:
            r = self.estado(*argumentos)
            self.assertEqual((r["etapa"], r["passo"], r["final"]), (etapa, passo, final), argumentos)
        self.assertIn("ONG Boa", self.estado("aprovada", "reservada", "aceito", "ONG Boa")["descricao"])

    def test_resposta_nao_traz_dados_pessoais(self):
        r = self.estado("aprovada", "reservada", "aceito", "ONG Boa")
        self.assertEqual(set(r), {"etapa", "passo", "titulo", "descricao", "final", "alimento", "quantidade_kg", "enviada_em"})

    def test_codigo_mal_formado_ou_inexistente_tem_a_mesma_resposta(self):
        for ruim in (None, 5, "", "curto", "a b" * 8, "x" * 65, "../../etc/passwd", "A" * 22 + "\n"):
            with self.assertRaises(publico_service.CodigoInvalido, msg=repr(ruim)):
                publico_service.acompanhar(ruim)
        with mock.patch.object(publico_service.oferta_repository, "acompanhar", return_value=None):
            with self.assertRaises(publico_service.CodigoInvalido):
                publico_service.acompanhar(self.CODIGO)
        with mock.patch.object(publico_service.oferta_repository, "acompanhar", side_effect=psycopg.errors.UndefinedTable("x")):
            with self.assertRaises(publico_service.CodigoInvalido):
                publico_service.acompanhar(self.CODIGO)


class AprovacaoTest(unittest.TestCase):
    def doacao(self, status="pendente", validade=None):
        return (4, 1, "Tomate", "hortifruti", 5.0, date.fromisoformat(validade or em(5)), status, None)

    def test_aprovar_e_recusar_so_pendentes(self):
        with mock.patch.object(doacao_service, "buscar_doacao", return_value=self.doacao()), \
                mock.patch.object(doacao_service.fluxo_repository, "atualizar_status_doacao", return_value=True) as muda:
            doacao_service.aprovar_doacao(4)
            muda.assert_called_with(4, "disponivel", "pendente")
            doacao_service.recusar_doacao(4)
            muda.assert_called_with(4, "cancelada", "pendente")
        for status in ("disponivel", "reservada", "concluida", "cancelada"):
            with mock.patch.object(doacao_service, "buscar_doacao", return_value=self.doacao(status)), \
                    mock.patch.object(doacao_service.fluxo_repository, "atualizar_status_doacao") as muda:
                for acao in (doacao_service.aprovar_doacao, doacao_service.recusar_doacao):
                    with self.assertRaises(ValueError):
                        acao(4)
                muda.assert_not_called()

    def test_nao_aprova_oferta_vencida_nem_com_status_trocado_por_outro(self):
        with mock.patch.object(doacao_service, "buscar_doacao", return_value=self.doacao(validade=em(-1))), \
                mock.patch.object(doacao_service.fluxo_repository, "atualizar_status_doacao") as muda:
            with self.assertRaisesRegex(ValueError, "validade"):
                doacao_service.aprovar_doacao(4)
            muda.assert_not_called()
        with mock.patch.object(doacao_service, "buscar_doacao", return_value=self.doacao()), \
                mock.patch.object(doacao_service.fluxo_repository, "atualizar_status_doacao", return_value=False):
            with self.assertRaisesRegex(ValueError, "mudou"):
                doacao_service.aprovar_doacao(4)

    def test_edicao_nao_volta_doacao_para_pendente(self):
        atual = self.doacao("disponivel")
        with mock.patch.object(doacao_service, "buscar_doacao", return_value=atual), \
                mock.patch.object(doacao_service, "atualizar_doacao"):
            with self.assertRaises(ValueError):
                doacao_service.editar_doacao(4, "Tomate", "hortifruti", 5, em(5), "pendente")


class PortalOngTest(unittest.TestCase):
    ONG = (2, "ONG Mesa Cheia", "o@o.org", None, "São Paulo", 100.0)

    def com_versao(self, versao=1):
        return mock.patch.object(ong_portal_service.fluxo_repository, "obter_info_link", return_value=(versao, None, True))

    def test_autenticacao(self):
        codigo = security.codigo_link_ong(2, 1)
        with mock.patch.object(ong_portal_service, "buscar_ong", return_value=self.ONG), self.com_versao(1):
            self.assertEqual(ong_portal_service.autenticar(2, codigo), self.ONG)
            for id_, cod in ((2, "errado"), (2, ""), (2, None), (3, codigo), (0, codigo), (-1, codigo), (True, codigo), ("2", codigo), (2 ** 40, codigo)):
                with self.assertRaises(ong_portal_service.AcessoNegado, msg=(id_, cod)):
                    ong_portal_service.autenticar(id_, cod)
        with mock.patch.object(ong_portal_service, "buscar_ong", return_value=self.ONG), self.com_versao(2):
            with self.assertRaises(ong_portal_service.AcessoNegado):
                ong_portal_service.autenticar(2, codigo)  # link antigo, depois de renovado
        with mock.patch.object(ong_portal_service, "buscar_ong", return_value=None), self.com_versao(1):
            with self.assertRaises(ong_portal_service.AcessoNegado):
                ong_portal_service.autenticar(2, codigo)

    def test_contato_do_doador_so_aparece_depois_do_aceite(self):
        linhas = [(i, status, "alta", "Tomate", "hortifruti", 10, date.fromisoformat(em(3)), "São Paulo", "Maria", "m@x.com", "(11) 91234-5678")
                  for i, status in ((1, "pendente"), (2, "aceito"), (3, "concluido"), (4, "recusado"))]
        with mock.patch.object(ong_portal_service.fluxo_repository, "matches_da_ong", return_value=linhas):
            itens = {m["id"]: m for m in ong_portal_service.painel(self.ONG)["matches"]}
        self.assertNotIn("doador", itens[1])
        self.assertNotIn("doador", itens[4])
        self.assertEqual(itens[2]["doador"]["email"], "m@x.com")
        self.assertIn("doador", itens[3])
        self.assertNotIn("score_ia", itens[1])

    def test_ong_so_responde_matches_dela_e_pendentes(self):
        match = lambda ong, status: (9, 5, ong, 0.8, "alta", status, None)
        vigente = (5, 1, "Tomate", "hortifruti", 10.0, date.fromisoformat(em(3)), "reservada", None)
        with mock.patch.object(ong_portal_service.match_service, "alterar_status_match") as altera, \
                mock.patch.object(ong_portal_service, "buscar_doacao", return_value=vigente):
            with mock.patch.object(ong_portal_service, "buscar_match", return_value=match(2, "pendente")):
                ong_portal_service.responder(self.ONG, 9, True)
                altera.assert_called_with(9, "aceito")
                ong_portal_service.responder(self.ONG, 9, False)
                altera.assert_called_with(9, "recusado")
            altera.reset_mock()
            with mock.patch.object(ong_portal_service, "buscar_match", return_value=match(3, "pendente")):
                with self.assertRaisesRegex(ValueError, "não encontrado"):
                    ong_portal_service.responder(self.ONG, 9, True)
            with mock.patch.object(ong_portal_service, "buscar_match", return_value=match(2, "aceito")):
                with self.assertRaises(ValueError):
                    ong_portal_service.responder(self.ONG, 9, False)
            with mock.patch.object(ong_portal_service, "buscar_match", return_value=None):
                with self.assertRaises(ValueError):
                    ong_portal_service.responder(self.ONG, 9, True)
            altera.assert_not_called()


class ConfirmacaoDeRecebimentoTest(unittest.TestCase):
    """A ONG conclui a propria entrega pelo portal; o registro guarda quem confirmou (ONG ou gestor)."""
    ONG = PortalOngTest.ONG

    def match(self, ong, status):
        return (9, 5, ong, 0.8, "alta", status, None)

    def test_ong_confirma_so_match_dela_e_aceito(self):
        with mock.patch.object(ong_portal_service.match_service, "alterar_status_match") as altera:
            with mock.patch.object(ong_portal_service, "buscar_match", return_value=self.match(2, "aceito")):
                ong_portal_service.confirmar_recebimento(self.ONG, 9)
                altera.assert_called_once_with(9, "concluido", origem="ong")
            altera.reset_mock()
            for atual, ong in (("pendente", 2), ("concluido", 2), ("recusado", 2), ("aceito", 3)):
                with mock.patch.object(ong_portal_service, "buscar_match", return_value=self.match(ong, atual)):
                    with self.assertRaises(ValueError, msg=(atual, ong)):
                        ong_portal_service.confirmar_recebimento(self.ONG, 9)
            with mock.patch.object(ong_portal_service, "buscar_match", return_value=None):
                with self.assertRaises(ValueError):
                    ong_portal_service.confirmar_recebimento(self.ONG, 9)
            for ruim in (0, -1, "9", True, None):
                with self.assertRaises(ValueError, msg=ruim):
                    ong_portal_service.confirmar_recebimento(self.ONG, ruim)
            altera.assert_not_called()

    def test_origem_so_e_gravada_ao_concluir(self):
        with mock.patch.object(match_service, "buscar_match", return_value=(9, 5, 2, 0.8, "alta", "aceito", None)), \
                mock.patch.object(match_service.fluxo_repository, "mudar_status_match") as muda:
            match_service.alterar_status_match(9, "concluido")
            muda.assert_called_with(9, "concluido", "aceito", "gestor")
            match_service.alterar_status_match(9, "concluido", origem="ong")
            muda.assert_called_with(9, "concluido", "aceito", "ong")
            match_service.alterar_status_match(9, "recusado", origem="ong")
            muda.assert_called_with(9, "recusado", "aceito", None)

    def test_conclusao_sobrevive_sem_a_migracao_006(self):
        """Sem a tabela match_confirmacoes, o savepoint desfaz so o registro; o status do match ja foi gravado."""
        comandos = []

        class Cursor:
            rowcount = 1

            def execute(self, comando, parametros=None):
                comandos.append(comando.split()[0:3])
                if comando.startswith("INSERT INTO match_confirmacoes"):
                    raise psycopg.errors.UndefinedTable("match_confirmacoes")

        fluxo_repository = match_service.fluxo_repository
        fluxo_repository._registrar_confirmacao(Cursor(), 9, "ong")
        self.assertEqual(comandos[0], ["SAVEPOINT", "confirmacao;"])
        self.assertEqual(comandos[-1], ["ROLLBACK", "TO", "SAVEPOINT"])


class DataDoLinkTest(unittest.TestCase):
    """O gestor ve de quando e o link da ONG (para decidir se renova); o link original nao tem data."""
    ONG = PortalOngTest.ONG

    def test_link_original_e_link_renovado(self):
        gerado = datetime(2026, 10, 15, 9, 30)
        with mock.patch.object(ong_portal_service, "buscar_ong", return_value=self.ONG):
            with mock.patch.object(ong_portal_service.fluxo_repository, "obter_info_link", return_value=(1, None, True)):
                original = ong_portal_service.link_da_ong(2)
            with mock.patch.object(ong_portal_service.fluxo_repository, "obter_info_link", return_value=(3, gerado, True)):
                renovado = ong_portal_service.link_da_ong(2)
            with mock.patch.object(ong_portal_service.fluxo_repository, "renovar_link", return_value=(4, gerado)):
                novo = ong_portal_service.renovar_link(2)
        self.assertEqual((original["versao"], original["gerado_em"]), (1, None))
        self.assertEqual((renovado["versao"], renovado["gerado_em"]), (3, gerado))
        self.assertEqual(novo["versao"], 4)
        # cada versao tem um codigo diferente: renovar invalida o link anterior
        self.assertEqual(len({original["caminho"], renovado["caminho"], novo["caminho"]}), 3)

    def test_sem_a_migracao_o_link_original_continua_valendo(self):
        with mock.patch.object(ong_portal_service, "buscar_ong", return_value=self.ONG), \
                mock.patch.object(ong_portal_service.fluxo_repository, "obter_info_link",
                                  side_effect=psycopg.errors.UndefinedTable("ong_links_acesso")):
            r = ong_portal_service.link_da_ong(2)
        self.assertEqual((r["versao"], r["gerado_em"]), (1, None))
        with mock.patch.object(ong_portal_service, "buscar_ong", return_value=self.ONG), \
                mock.patch.object(ong_portal_service.fluxo_repository, "renovar_link",
                                  side_effect=psycopg.errors.UndefinedTable("ong_links_acesso")):
            with self.assertRaisesRegex(ValueError, "migração"):
                ong_portal_service.renovar_link(2)


class RegrasExtrasTest(unittest.TestCase):
    def test_ong_nao_aceita_doacao_vencida_mas_pode_recusar(self):
        vencida = (5, 1, "Tomate", "hortifruti", 10.0, date.fromisoformat(em(-1)), "reservada", None)
        with mock.patch.object(ong_portal_service, "buscar_match", return_value=(9, 5, 2, 0.8, "alta", "pendente", None)), \
                mock.patch.object(ong_portal_service, "buscar_doacao", return_value=vencida), \
                mock.patch.object(ong_portal_service.match_service, "alterar_status_match") as altera:
            with self.assertRaisesRegex(ValueError, "validade"):
                ong_portal_service.responder(PortalOngTest.ONG, 9, True)
            altera.assert_not_called()
            ong_portal_service.responder(PortalOngTest.ONG, 9, False)
            altera.assert_called_once_with(9, "recusado")

    def test_exclusoes_nao_apagam_historico(self):
        from services import doador_service, ong_service
        doacao = (7, 1, "Doador", "Tomate", "hortifruti", 5.0, em(5), "concluida", None)
        match = (3, 7, "Tomate", 2, "ONG", 0.5, "alta", "concluido", None)
        with mock.patch.object(doador_service, "buscar_doador", return_value=(1,)), \
                mock.patch.object(doador_service, "listar_doacoes", return_value=[doacao]), \
                mock.patch.object(doador_service, "excluir_doador") as exclui:
            with self.assertRaisesRegex(ValueError, "doações"):
                doador_service.remover_doador(1)
            exclui.assert_not_called()
        with mock.patch.object(doador_service, "buscar_doador", return_value=(9,)), \
                mock.patch.object(doador_service, "listar_doacoes", return_value=[doacao]), \
                mock.patch.object(doador_service, "excluir_doador") as exclui:
            doador_service.remover_doador(9)
            exclui.assert_called_once_with(9)
        with mock.patch.object(ong_service, "buscar_ong", return_value=(2,)), \
                mock.patch.object(ong_service, "listar_matches", return_value=[match]), \
                mock.patch.object(ong_service, "excluir_ong") as exclui:
            with self.assertRaisesRegex(ValueError, "matches"):
                ong_service.remover_ong(2)
            exclui.assert_not_called()
        with mock.patch.object(doacao_service, "buscar_doacao", return_value=(7, 1, "Tomate", "hortifruti", 5.0, em(5), "concluida", None)), \
                mock.patch.object(doacao_service, "listar_matches", return_value=[match]), \
                mock.patch.object(doacao_service, "excluir_doacao") as exclui:
            with self.assertRaisesRegex(ValueError, "matches"):
                doacao_service.remover_doacao(7)
            exclui.assert_not_called()


class EndpointsNovosTest(SemIA):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.make_server("127.0.0.1", 0)
        server.API_TOKEN = TOKEN
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        super().setUp()
        server.REQUEST_LIMITER = security.RateLimiter(300, 60)
        server.AUTH_FAIL_LIMITER = security.RateLimiter(10, 60)
        server.PUBLIC_LIMITER = security.RateLimiter(5, 3600)
        server.PUBLIC_ATTEMPTS_LIMITER = security.RateLimiter(40, 3600)
        server.PUBLIC_GLOBAL_LIMITER = security.RateLimiter(100, 3600)
        server.ACOMPANHAR_LIMITER = security.RateLimiter(20, 600)

    def call(self, method, path, body=None, headers=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        cabecalhos = {"Content-Type": "application/json", **(headers or {})}
        conn.request(method, path, body=raw if raw is not None else (json.dumps(body) if body is not None else None), headers=cabecalhos)
        resposta = conn.getresponse()
        texto = resposta.read().decode()
        conn.close()
        try:
            return resposta.status, json.loads(texto)
        except ValueError:
            return resposta.status, texto

    def test_paginas_publicas_existem(self):
        for caminho in ("/", "/admin", "/doar", "/doar.js", "/ong", "/ong.js", "/acompanhar", "/acompanhar.js", "/privacidade"):
            status, _ = self.call("GET", caminho)
            self.assertEqual(status, 200, caminho)

    def test_oferta_publica_sem_token(self):
        with mock.patch.object(publico_service.oferta_repository, "criar", return_value=1):
            status, corpo = self.call("POST", "/api/publico/doacoes", OFERTA)
        self.assertEqual(status, 201)
        self.assertEqual(set(corpo), {"mensagem", "codigo"})

    def test_oferta_publica_exige_json_e_corpo_pequeno_e_rota_certa(self):
        self.assertEqual(self.call("POST", "/api/publico/doacoes", raw="nome=x", headers={"Content-Type": "text/plain"})[0], 400)
        self.assertEqual(self.call("POST", "/api/publico/doacoes", raw=json.dumps({"x": "a" * 9000}))[0], 400)
        self.assertEqual(self.call("POST", "/api/publico/doacoes", raw="{\"quantidade_kg\": NaN}")[0], 400)
        self.assertEqual(self.call("GET", "/api/publico/doacoes")[0], 404)
        self.assertEqual(self.call("POST", "/api/publico/outra", OFERTA)[0], 404)
        self.assertEqual(self.call("POST", "/api/publico/doacoes", {**OFERTA, "status": "disponivel"})[0], 400)

    def test_oferta_publica_tem_limite_por_ip(self):
        with mock.patch.object(publico_service.oferta_repository, "criar", return_value=1):
            codigos = [self.call("POST", "/api/publico/doacoes", {**OFERTA, "site": "robo"})[0] for _ in range(7)]
        self.assertEqual(codigos[:5], [201] * 5)
        self.assertEqual(codigos[5:], [429, 429])

    def test_oferta_publica_nao_da_acesso_ao_painel(self):
        for metodo, caminho in (("GET", "/api/doacoes"), ("GET", "/api/doadores"), ("GET", "/api/matches"), ("POST", "/api/doacoes/1/aprovar"),
                                ("GET", "/api/ongs/1/link"), ("POST", "/api/ongs/1/link/renovar"), ("GET", "/api/indicadores"),
                                ("GET", "/api/ofertas"), ("POST", "/api/ofertas/1/aprovar"), ("POST", "/api/ofertas/1/recusar")):
            self.assertEqual(self.call(metodo, caminho)[0], 401, caminho)

    def test_acompanhar_oferta_sem_token_e_sem_dados_pessoais(self):
        resposta = {"etapa": "analise", "passo": 1, "titulo": "t", "descricao": "d", "final": False,
                    "alimento": "Tomate", "quantidade_kg": 12.0, "enviada_em": datetime(2026, 10, 14, 9)}
        with mock.patch.object(publico_service, "acompanhar", return_value=resposta) as consulta:
            status, corpo = self.call("POST", "/api/publico/acompanhar", {"codigo": "A" * 22})
        self.assertEqual(status, 200)
        self.assertEqual(corpo["etapa"], "analise")
        self.assertNotIn("email", json.dumps(corpo))
        consulta.assert_called_once_with("A" * 22)

    def test_acompanhar_codigo_errado_responde_404_e_bloqueia_adivinhacao(self):
        with mock.patch.object(publico_service.oferta_repository, "acompanhar", return_value=None):
            codigos = [self.call("POST", "/api/publico/acompanhar", {"codigo": f"{i:022d}"})[0] for i in range(24)]
        self.assertEqual(codigos[:20], [404] * 20)
        self.assertEqual(codigos[20:], [429] * 4)

    def test_acompanhar_exige_json_pequeno_e_so_aceita_post(self):
        self.assertEqual(self.call("POST", "/api/publico/acompanhar", raw="codigo=x", headers={"Content-Type": "text/plain"})[0], 400)
        self.assertEqual(self.call("POST", "/api/publico/acompanhar", raw=json.dumps({"codigo": "a" * 2000}))[0], 400)
        self.assertEqual(self.call("GET", "/api/publico/acompanhar")[0], 404)
        self.assertEqual(self.call("POST", "/api/publico/acompanhar", {})[0], 404)  # sem codigo: mesma resposta de codigo errado

    def test_admin_lista_aprova_e_recusa_ofertas(self):
        cab = {"Authorization": "Bearer " + TOKEN}
        with mock.patch.object(oferta_service, "listar", return_value=[{"id": 4}]), \
                mock.patch.object(oferta_service, "aprovar", return_value=9) as aprova, \
                mock.patch.object(oferta_service, "recusar") as recusa:
            self.assertEqual(self.call("GET", "/api/ofertas", headers=cab), (200, [{"id": 4}]))
            self.assertEqual(self.call("POST", "/api/ofertas/4/aprovar", {}, cab), (200, {"ok": True, "doacao_id": 9}))
            self.assertEqual(self.call("POST", "/api/ofertas/4/recusar", {}, cab), (200, {"ok": True}))
            aprova.assert_called_once_with(4)
            recusa.assert_called_once_with(4)
        with mock.patch.object(oferta_service.oferta_repository, "aprovar", side_effect=ValueError("A validade desta oferta já passou.")):
            status, corpo = self.call("POST", "/api/ofertas/4/aprovar", {}, cab)
        self.assertEqual(status, 400)
        self.assertIn("validade", corpo["error"])

    def test_portal_da_ong_exige_link_valido(self):
        with mock.patch.object(ong_portal_service, "buscar_ong", return_value=PortalOngTest.ONG), \
                mock.patch.object(ong_portal_service.fluxo_repository, "obter_info_link", return_value=(1, None, True)), \
                mock.patch.object(ong_portal_service.fluxo_repository, "matches_da_ong", return_value=[]):
            bom = {"X-Ong-Id": "2", "X-Ong-Codigo": security.codigo_link_ong(2, 1)}
            self.assertEqual(self.call("GET", "/api/ong-portal/matches", headers=bom)[0], 200)
            for ruim in ({}, {"X-Ong-Id": "2"}, {"X-Ong-Id": "2", "X-Ong-Codigo": "x"}, {"X-Ong-Id": "abc", "X-Ong-Codigo": "x"},
                         {"X-Ong-Id": "3", "X-Ong-Codigo": bom["X-Ong-Codigo"]}):
                self.assertEqual(self.call("GET", "/api/ong-portal/matches", headers=ruim)[0], 401, ruim)
            self.assertEqual(self.call("GET", "/api/doacoes", headers=bom)[0], 401)  # o link da ONG nao abre o painel do gestor
            self.assertEqual(self.call("GET", "/api/ong-portal/outra", headers=bom)[0], 404)
            with mock.patch.object(ong_portal_service, "confirmar_recebimento") as confirma:
                self.assertEqual(self.call("POST", "/api/ong-portal/matches/9/receber", {}, bom)[0], 200)
                confirma.assert_called_once_with(PortalOngTest.ONG, 9)
            self.assertEqual(self.call("POST", "/api/ong-portal/matches/9/receber", {}, {"X-Ong-Id": "2", "X-Ong-Codigo": "x"})[0], 401)

    def test_portal_bloqueia_tentativas_de_adivinhar_codigo(self):
        with mock.patch.object(ong_portal_service, "buscar_ong", return_value=PortalOngTest.ONG), \
                mock.patch.object(ong_portal_service.fluxo_repository, "obter_info_link", return_value=(1, None, True)):
            codigos = [self.call("GET", "/api/ong-portal/matches", headers={"X-Ong-Id": "2", "X-Ong-Codigo": f"c{i}"})[0] for i in range(14)]
        self.assertEqual(codigos[:10], [401] * 10)
        self.assertIn(429, codigos[10:])

    def test_admin_aprova_e_gera_link(self):
        cab = {"Authorization": "Bearer " + TOKEN}
        with mock.patch.object(doacao_service, "aprovar_doacao") as aprova, mock.patch.object(doacao_service, "recusar_doacao") as recusa:
            self.assertEqual(self.call("POST", "/api/doacoes/4/aprovar", {}, cab)[0], 200)
            self.assertEqual(self.call("POST", "/api/doacoes/4/recusar", {}, cab)[0], 200)
            aprova.assert_called_once_with(4)
            recusa.assert_called_once_with(4)
        with mock.patch.object(ong_portal_service, "buscar_ong", return_value=PortalOngTest.ONG), \
                mock.patch.object(ong_portal_service.fluxo_repository, "obter_info_link", return_value=(1, None, True)):
            status, corpo = self.call("GET", "/api/ongs/2/link", headers=cab)
        self.assertEqual(status, 200)
        self.assertEqual(corpo["caminho"], "/ong#2." + security.codigo_link_ong(2, 1))
        self.assertEqual((corpo["versao"], corpo["gerado_em"]), (1, None))  # link original: valido desde o cadastro


if __name__ == "__main__":
    unittest.main()
