"""Contas individuais (gestor e ONG): senhas, sessoes, login, perfis, troca de senha e auditoria. Sem banco."""
import http.client
import json
import os
import sys
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TOKEN = "c" * 40
os.environ["API_TOKEN"] = TOKEN

import security  # noqa: E402
import server  # noqa: E402
from services import autenticacao_service as auth, ong_portal_service  # noqa: E402


def rapido():
    """PBKDF2 com poucas iteracoes so nos testes (o valor real, 600 mil, leva ~0,2 s por senha)."""
    return mock.patch.object(security, "ITERACOES_SENHA", 1000)


# (id, perfil, ong_id, nome, email, ativo, trocar_senha, nome_da_ong)
GESTOR = (1, "gestor", None, "Ana Gestora", "ana@rede.org", True, False, None)
ONG = (2, "ong", 7, "Bia da ONG", "bia@ong.org", True, False, "ONG Boa")


class SenhasTest(unittest.TestCase):
    def test_hash_confere_e_nao_guarda_a_senha(self):
        with rapido():
            h = security.hash_senha("uma senha longa 2026")
            self.assertTrue(security.verificar_senha("uma senha longa 2026", h))
            self.assertFalse(security.verificar_senha("uma senha longa 2027", h))
            self.assertNotIn("uma senha longa", h)
            self.assertNotEqual(h, security.hash_senha("uma senha longa 2026"))  # sal aleatorio

    def test_hash_malformado_ou_entrada_estranha_nunca_levanta(self):
        for armazenado in ("", "lixo", "a$b$c$d", "pbkdf2_sha256$x$y$z", None, 5, "pbkdf2_sha256$1000$!!$!!"):
            self.assertFalse(security.verificar_senha("qualquer", armazenado), armazenado)
        with rapido():
            h = security.hash_senha("uma senha longa 2026")
        for senha in (None, 5, b"x", ["x"]):
            self.assertFalse(security.verificar_senha(senha, h), senha)

    def test_iteracoes_ficam_no_hash(self):
        with mock.patch.object(security, "ITERACOES_SENHA", 1234):
            h = security.hash_senha("uma senha longa 2026")
        self.assertEqual(h.split("$")[1], "1234")
        self.assertTrue(security.verificar_senha("uma senha longa 2026", h))  # valendo com o valor padrao diferente

    def test_politica_de_senha(self):
        ruins = ["curta", "1234567890", "aaaaaaaaaaaa", "Senha12345", "x" * 200, None, 12345678901]
        for ruim in ruins:
            self.assertIsNotNone(security.problema_na_senha(ruim, "ana@rede.org", "Ana"), ruim)
        self.assertIsNotNone(security.problema_na_senha("minha-bia.silva-9", "bia.silva@x.org", "Bia"))  # contem o e-mail
        self.assertIsNotNone(security.problema_na_senha("Mariana2026!!", "m@x.org", "Mariana Souza"))  # comeca com o nome
        self.assertIsNone(security.problema_na_senha("trilha azul 7788", "ana@rede.org", "Ana"))

    def test_senha_provisoria_e_token_de_sessao(self):
        senhas = {security.senha_provisoria() for _ in range(50)}
        self.assertEqual(len(senhas), 50)
        for senha in senhas:
            self.assertEqual(len(senha), 12)
            self.assertFalse(set(senha) & set("0O1lI"))
        token, hash_ = security.novo_token_sessao()
        self.assertTrue(token.startswith("u1."))
        self.assertEqual(hash_, security.hash_token(token))
        self.assertNotIn(token, hash_)
        self.assertEqual(len(hash_), 64)


class LoginTest(unittest.TestCase):
    def setUp(self):
        auth.LOGIN_LIMITER = security.RateLimiter(5, 900)
        with rapido():
            self.hash = security.hash_senha("senha certa 2026")

    def linha(self, ativo=True):
        return (1, "gestor", None, "Ana Gestora", "ana@rede.org", ativo, False, None, self.hash)

    def entrar(self, email, senha, linha="padrao"):
        linha = self.linha() if linha == "padrao" else linha
        with mock.patch.object(auth.usuario_repository, "buscar_para_login", return_value=linha), \
                mock.patch.object(auth.usuario_repository, "criar_sessao") as cria, \
                mock.patch.object(auth.usuario_repository, "registrar_acesso"):
            return auth.login(email, senha), cria

    def test_login_certo_abre_sessao_e_guarda_so_o_hash(self):
        resposta, cria = self.entrar("  ANA@rede.org ", "senha certa 2026")
        self.assertTrue(resposta["token"].startswith("u1."))
        self.assertEqual(resposta["expira_em"], 12 * 3600)
        self.assertEqual(resposta["usuario"]["perfil"], "gestor")
        self.assertNotIn("senha_hash", json.dumps(resposta))
        id_, hash_gravado, segundos = cria.call_args.args
        self.assertEqual((id_, hash_gravado, segundos), (1, security.hash_token(resposta["token"]), 12 * 3600))

    def test_todos_os_erros_tem_a_mesma_resposta(self):
        casos = [("ana@rede.org", "senha errada 2026", "padrao"), ("nao@existe.org", "senha certa 2026", None),
                 ("ana@rede.org", "senha certa 2026", self.linha(ativo=False))]
        for email, senha, linha in casos:
            with self.assertRaises(auth.CredenciaisInvalidas, msg=(email, linha is None)):
                self.entrar(email, senha, linha)
        for estranho in (None, 5, "", "   ", "x" * 300):
            with self.assertRaises(auth.CredenciaisInvalidas):
                auth.login(estranho, "senha certa 2026")
        with self.assertRaises(auth.CredenciaisInvalidas):
            auth.login("ana@rede.org", None)

    def test_email_inexistente_tambem_gasta_o_calculo_da_senha(self):
        with mock.patch.object(auth.security, "verificar_senha", return_value=False) as confere:
            with self.assertRaises(auth.CredenciaisInvalidas):
                self.entrar("nao@existe.org", "qualquer coisa 123", None)
        confere.assert_called_once()
        self.assertEqual(confere.call_args.args[1], security.hash_falso())  # mesmo trabalho de um e-mail que existe

    def test_cinco_falhas_bloqueiam_o_email_exista_ele_ou_nao(self):
        for email in ("ana@rede.org", "fantasma@rede.org"):
            for _ in range(5):
                with self.assertRaises(auth.CredenciaisInvalidas):
                    self.entrar(email, "errada errada 1", self.linha() if email.startswith("ana") else None)
            with self.assertRaises(auth.LoginBloqueado) as bloqueio:
                self.entrar(email, "senha certa 2026", self.linha() if email.startswith("ana") else None)
            self.assertGreater(bloqueio.exception.segundos, 0)  # inclusive com a senha certa: a resposta nao revela nada

    def test_sem_a_migracao_avisa(self):
        with mock.patch.object(auth.usuario_repository, "buscar_para_login", side_effect=psycopg.errors.UndefinedTable("usuarios")):
            with self.assertRaises(auth.ContasIndisponiveis):
                auth.login("ana@rede.org", "senha certa 2026")


class SessaoTest(unittest.TestCase):
    def test_identificar(self):
        with mock.patch.object(auth.usuario_repository, "buscar_sessao", return_value=GESTOR) as busca:
            ator = auth.identificar("u1." + "a" * 43)
        self.assertEqual((ator["tipo"], ator["perfil"], ator["nome"]), ("usuario", "gestor", "Ana Gestora"))
        self.assertEqual(busca.call_args.args[0], security.hash_token("u1." + "a" * 43))  # o banco so ve o hash
        with mock.patch.object(auth.usuario_repository, "buscar_sessao", return_value=None):
            self.assertIsNone(auth.identificar("u1." + "a" * 43))  # vencida ou inexistente
        with mock.patch.object(auth.usuario_repository, "buscar_sessao", return_value=(1, "gestor", None, "Ana", "a@x.org", False, False, None)):
            self.assertIsNone(auth.identificar("u1." + "a" * 43))  # conta desativada: a sessao morre na hora
        with mock.patch.object(auth.usuario_repository, "buscar_sessao") as busca:
            for ruim in (None, 5, "", "s1.123.abc", "Bearer u1.x", "u1." + "a" * 200):
                self.assertIsNone(auth.identificar(ruim), ruim)
            busca.assert_not_called()  # token que nem parece de conta nao chega ao banco
        with mock.patch.object(auth.usuario_repository, "buscar_sessao", side_effect=psycopg.errors.UndefinedTable("x")):
            self.assertIsNone(auth.identificar("u1." + "a" * 43))

    def test_logout_apaga_a_sessao(self):
        with mock.patch.object(auth.usuario_repository, "apagar_sessao") as apaga:
            auth.logout("u1.abc")
            apaga.assert_called_once_with(security.hash_token("u1.abc"))
            apaga.reset_mock()
            auth.logout("s1.1.2")  # sessao da senha mestre nao esta no banco
            auth.logout(None)
            apaga.assert_not_called()


class TrocaDeSenhaTest(unittest.TestCase):
    def setUp(self):
        auth.LOGIN_LIMITER = security.RateLimiter(5, 900)
        with rapido():
            self.hash = security.hash_senha("senha atual 2026")
        self.ator = auth._ator(GESTOR)

    def trocar(self, atual, nova):
        with mock.patch.object(auth.usuario_repository, "senha_hash_de", return_value=self.hash), \
                mock.patch.object(auth.usuario_repository, "atualizar_senha") as atualiza, \
                mock.patch.object(auth.usuario_repository, "apagar_sessoes_do_usuario") as apaga:
            with rapido():
                auth.trocar_senha(self.ator, atual, nova, "u1.minha")
            return atualiza, apaga

    def test_troca_grava_hash_novo_e_derruba_as_outras_sessoes(self):
        atualiza, apaga = self.trocar("senha atual 2026", "outra senha 2027")
        id_, novo_hash, trocar = atualiza.call_args.args
        self.assertEqual((id_, trocar), (1, False))
        self.assertTrue(security.verificar_senha("outra senha 2027", novo_hash))
        self.assertNotIn("outra senha", novo_hash)
        apaga.assert_called_once_with(1, manter_hash=security.hash_token("u1.minha"))

    def test_recusas(self):
        for atual, nova, trecho in (("errada errada 1", "outra senha 2027", "atual"), ("senha atual 2026", "curta", "caracteres"),
                                    ("senha atual 2026", "senha atual 2026", "diferente")):
            with self.assertRaisesRegex(ValueError, trecho, msg=(atual, nova)):
                self.trocar(atual, nova)

    def test_token_da_api_nao_e_conta(self):
        with self.assertRaisesRegex(ValueError, "token"):
            auth.trocar_senha(auth.ATOR_TOKEN, "x", "outra senha 2027", "token")

    def test_adivinhar_a_senha_atual_tem_limite(self):
        with mock.patch.object(auth.usuario_repository, "senha_hash_de", return_value=self.hash):
            for _ in range(5):
                with self.assertRaisesRegex(ValueError, "incorreta"):
                    auth.trocar_senha(self.ator, "chute chute 11", "outra senha 2027", "u1.minha")
            with self.assertRaisesRegex(ValueError, "Muitas tentativas"):
                auth.trocar_senha(self.ator, "senha atual 2026", "outra senha 2027", "u1.minha")


class GestaoDeAcessosTest(unittest.TestCase):
    def test_gestor_cria_conta_com_senha_provisoria_que_so_o_hash_fica_no_banco(self):
        with mock.patch.object(auth.usuario_repository, "criar", return_value=9) as cria, rapido():
            r = auth.criar_usuario("gestor", "  Caio   Souza ", "Caio@Rede.org")
        perfil, ong_id, nome, email, hash_, trocar = cria.call_args.args
        self.assertEqual((perfil, ong_id, nome, email, trocar), ("gestor", None, "Caio Souza", "caio@rede.org", True))
        self.assertEqual(r["id"], 9)
        self.assertTrue(security.verificar_senha(r["senha_provisoria"], hash_))
        self.assertNotIn(r["senha_provisoria"], hash_)

    def test_conta_de_ong_exige_ong_existente_e_tem_limite(self):
        with mock.patch.object(auth, "buscar_ong", return_value=None), self.assertRaisesRegex(ValueError, "não encontrada"):
            auth.criar_usuario("ong", "Dani Souza", "dani@ong.org", 7)
        with mock.patch.object(auth, "buscar_ong", return_value=(7, "ONG Boa")), \
                mock.patch.object(auth.usuario_repository, "contar_ativos", return_value=auth.MAX_CONTAS_ONG), \
                self.assertRaisesRegex(ValueError, "contas ativas"):
            auth.criar_usuario("ong", "Dani Souza", "dani@ong.org", 7)
        for ruim in ({"perfil": "admin"}, {"perfil": "ong", "ong_id": None}, {"perfil": "gestor", "nome": "<b>x</b>"},
                     {"perfil": "gestor", "email": "sem-arroba"}, {"perfil": 5}):
            dados = {"perfil": "gestor", "nome": "Caio Souza", "email": "caio@rede.org", "ong_id": None, **ruim}
            with mock.patch.object(auth.usuario_repository, "criar", return_value=1) as cria:
                with self.assertRaises(ValueError, msg=ruim):
                    auth.criar_usuario(**dados)
                cria.assert_not_called()

    def test_conta_de_gestor_ignora_ong_id(self):
        with mock.patch.object(auth.usuario_repository, "criar", return_value=1) as cria, rapido():
            auth.criar_usuario("gestor", "Caio Souza", "caio@rede.org", 99)
        self.assertIsNone(cria.call_args.args[1])

    def test_email_repetido_e_banco_sem_migracao(self):
        with mock.patch.object(auth.usuario_repository, "criar", side_effect=psycopg.errors.UniqueViolation("x")), rapido():
            with self.assertRaisesRegex(ValueError, "Já existe"):
                auth.criar_usuario("gestor", "Caio Souza", "caio@rede.org")
        with mock.patch.object(auth.usuario_repository, "criar", side_effect=psycopg.errors.UndefinedTable("x")), rapido():
            with self.assertRaises(auth.ContasIndisponiveis):
                auth.criar_usuario("gestor", "Caio Souza", "caio@rede.org")

    def test_ong_cria_a_propria_conta_pelo_link_e_ja_entra(self):
        ong = (7, "ONG Boa", "o@o.org", None, "Santos", 100)
        linha = (5, "ong", 7, "Dani Souza", "dani@ong.org", True, False, "ONG Boa", "h")
        with mock.patch.object(auth, "buscar_ong", return_value=ong), \
                mock.patch.object(auth.usuario_repository, "contar_ativos", return_value=0), \
                mock.patch.object(auth.usuario_repository, "criar", return_value=5) as cria, \
                mock.patch.object(auth.usuario_repository, "buscar_para_login", return_value=linha), \
                mock.patch.object(auth.usuario_repository, "criar_sessao"), \
                mock.patch.object(auth.usuario_repository, "registrar_acesso"), rapido():
            r = auth.criar_conta_ong_pelo_link(ong, "Dani Souza", "dani@ong.org", "trilha azul 7788")
            self.assertEqual((cria.call_args.args[0], cria.call_args.args[1], cria.call_args.args[5]), ("ong", 7, False))
            self.assertTrue(security.verificar_senha("trilha azul 7788", cria.call_args.args[4]))
            self.assertTrue(r["token"].startswith("u1."))
            with self.assertRaisesRegex(ValueError, "senha"):  # a senha da propria pessoa tambem passa pela politica
                auth.criar_conta_ong_pelo_link(ong, "Dani Souza", "dani@ong.org", "1234567890")

    def test_desativar_protege_a_si_mesmo_e_o_ultimo_gestor(self):
        ator = auth._ator(GESTOR)
        with mock.patch.object(auth.usuario_repository, "buscar", return_value=(1, "gestor", None, "Ana", "a@x.org", True, False, None, None, None)), \
                mock.patch.object(auth.usuario_repository, "definir_ativo") as define:
            with self.assertRaisesRegex(ValueError, "própria conta"):
                auth.desativar(1, ator)
            with mock.patch.object(auth.usuario_repository, "contar_ativos", return_value=1), \
                    self.assertRaisesRegex(ValueError, "única conta de gestor"):
                auth.desativar(1, auth.ATOR_TOKEN)
            define.assert_not_called()
            with mock.patch.object(auth.usuario_repository, "contar_ativos", return_value=2):
                auth.desativar(1, auth.ATOR_TOKEN)
            define.assert_called_once_with(1, False)
        with mock.patch.object(auth.usuario_repository, "buscar", return_value=None), self.assertRaisesRegex(ValueError, "não encontrada"):
            auth.desativar(99, ator)
        for ruim in (0, -1, "1", True):
            with self.assertRaises(ValueError, msg=ruim):
                auth.desativar(ruim, ator)

    def test_redefinir_senha_forca_troca_e_derruba_sessoes(self):
        with mock.patch.object(auth.usuario_repository, "buscar", return_value=(2, "ong", 7, "Bia", "b@o.org", True, False, "ONG", None, None)), \
                mock.patch.object(auth.usuario_repository, "atualizar_senha") as atualiza, \
                mock.patch.object(auth.usuario_repository, "apagar_sessoes_do_usuario") as apaga, rapido():
            r = auth.redefinir_senha(2)
        id_, hash_, trocar = atualiza.call_args.args
        self.assertEqual((id_, trocar), (2, True))
        self.assertTrue(security.verificar_senha(r["senha_provisoria"], hash_))
        apaga.assert_called_once_with(2)


class AuditoriaTest(unittest.TestCase):
    def test_registrar_nunca_levanta(self):
        with mock.patch.object(auth.usuario_repository, "registrar_auditoria", side_effect=RuntimeError("banco fora")):
            with self.assertLogs(level="WARNING"):
                auth.registrar_auditoria(auth.ATOR_TOKEN, "POST /api/x")

    def test_registrar_corta_textos_longos(self):
        with mock.patch.object(auth.usuario_repository, "registrar_auditoria") as grava:
            auth.registrar_auditoria({**auth.ATOR_TOKEN, "nome": "n" * 500}, "a" * 500, "x", 3, "1.2.3.4")
        tipo, id_, nome, acao, recurso, registro, ip = grava.call_args.args
        self.assertEqual((len(nome), len(acao), recurso, registro, ip), (160, 120, "x", 3, "1.2.3.4"))

    def test_limite_da_listagem(self):
        with mock.patch.object(auth.usuario_repository, "listar_auditoria", return_value=[]) as lista:
            for entrada, esperado in ((None, 200), ("abc", 200), (0, 1), (-5, 1), ("50", 50), (10 ** 9, 500)):
                auth.auditoria(entrada)
                self.assertEqual(lista.call_args.args[0], esperado, entrada)


class LinkDaOngTest(unittest.TestCase):
    ONG_TUPLA = (7, "ONG Boa", "o@o.org", None, "Santos", 100.0)

    def test_link_desativado_nao_autentica_e_gerar_novo_reativa(self):
        codigo = security.codigo_link_ong(7, 1)
        with mock.patch.object(ong_portal_service, "buscar_ong", return_value=self.ONG_TUPLA):
            with mock.patch.object(ong_portal_service.fluxo_repository, "obter_info_link", return_value=(1, None, True)):
                self.assertEqual(ong_portal_service.autenticar(7, codigo), self.ONG_TUPLA)
            with mock.patch.object(ong_portal_service.fluxo_repository, "obter_info_link", return_value=(1, None, False)):
                with self.assertRaises(ong_portal_service.AcessoNegado):
                    ong_portal_service.autenticar(7, codigo)
            with mock.patch.object(ong_portal_service.fluxo_repository, "renovar_link", return_value=(2, datetime(2026, 10, 15))):
                novo = ong_portal_service.renovar_link(7)
        self.assertTrue(novo["ativo"])

    def test_desativar_link(self):
        with mock.patch.object(ong_portal_service, "buscar_ong", return_value=self.ONG_TUPLA), \
                mock.patch.object(ong_portal_service.fluxo_repository, "definir_link_ativo") as define, \
                mock.patch.object(ong_portal_service.fluxo_repository, "obter_info_link", return_value=(1, None, False)):
            r = ong_portal_service.desativar_link(7)
        define.assert_called_once_with(7, False)
        self.assertFalse(r["ativo"])
        with mock.patch.object(ong_portal_service, "buscar_ong", return_value=self.ONG_TUPLA), \
                mock.patch.object(ong_portal_service.fluxo_repository, "definir_link_ativo", side_effect=psycopg.errors.UndefinedColumn("ativo")):
            with self.assertRaisesRegex(ValueError, "migração 007"):
                ong_portal_service.desativar_link(7)
        with mock.patch.object(ong_portal_service, "buscar_ong", return_value=None), self.assertRaisesRegex(ValueError, "não encontrada"):
            ong_portal_service.desativar_link(7)

    def test_conta_de_ong_cuja_ong_foi_excluida_perde_o_acesso(self):
        with mock.patch.object(ong_portal_service, "buscar_ong", return_value=None):
            with self.assertRaises(ong_portal_service.AcessoNegado):
                ong_portal_service.ong_da_conta({"ong_id": 7})
            with self.assertRaises(ong_portal_service.AcessoNegado):
                ong_portal_service.ong_da_conta({"ong_id": None})

    def test_repositorio_cai_no_sql_antigo_sem_a_coluna_ativo(self):
        from repositories import fluxo_repository as repo
        chamadas = []

        def transacao(funcao):
            chamadas.append(funcao.__name__)
            if funcao.__name__ == "operacao":
                raise psycopg.errors.UndefinedColumn("ativo")

            class Cursor:
                def execute(self, *args):
                    pass

                def fetchone(self):
                    return (3, datetime(2026, 10, 15), True)

            return funcao(Cursor())

        with mock.patch.object(repo, "_transacao", side_effect=transacao):
            self.assertEqual(repo.obter_info_link(7), (3, datetime(2026, 10, 15), True))  # versao > 1: tem data; ativo por padrao
            self.assertEqual(repo.renovar_link(7), (3, datetime(2026, 10, 15)))
        self.assertEqual(chamadas, ["operacao", "sem_a_coluna_ativo", "operacao", "sem_a_coluna_ativo"])

    def test_link_original_nao_tem_data_mesmo_que_a_linha_exista(self):
        from repositories import fluxo_repository as repo
        with mock.patch.object(repo, "_transacao", return_value=(1, datetime(2026, 10, 1), False)):
            self.assertEqual(repo.obter_info_link(7), (1, None, False))  # desativar um link original cria a linha, sem "datar" o link
        with mock.patch.object(repo, "_transacao", return_value=None):
            self.assertEqual(repo.obter_info_link(7), (1, None, True))


class ServidorBase(unittest.TestCase):
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
        server.REQUEST_LIMITER = security.RateLimiter(300, 60)
        server.AUTH_FAIL_LIMITER = security.RateLimiter(10, 60)
        auth.LOGIN_LIMITER = security.RateLimiter(5, 900)
        # Outros modulos de teste trocam API_TOKEN no ambiente ao serem importados; aqui vale o deste modulo.
        ambiente = mock.patch.dict(os.environ, {"API_TOKEN": TOKEN})
        ambiente.start()
        self.addCleanup(ambiente.stop)
        server.API_TOKEN = TOKEN

    def call(self, metodo, caminho, corpo=None, token=None, cabecalhos=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = {"Content-Type": "application/json", **(cabecalhos or {})}
        if token:
            h["Authorization"] = "Bearer " + token
        conn.request(metodo, caminho, body=json.dumps(corpo) if corpo is not None else None, headers=h)
        r = conn.getresponse()
        texto = r.read().decode()
        conn.close()
        try:
            return r.status, json.loads(texto)
        except ValueError:
            return r.status, texto

    def como(self, linha):
        """Faz o servidor enxergar uma sessao de conta com os dados dessa linha."""
        return mock.patch.object(server.autenticacao_service.usuario_repository, "buscar_sessao", return_value=linha)


class LoginHttpTest(ServidorBase):
    def test_nao_existe_senha_mestre(self):
        for corpo in ({"senha": TOKEN}, {"email": "", "senha": TOKEN}, {"email": None, "senha": TOKEN}):
            self.assertEqual(self.call("POST", "/api/login", corpo)[0], 401, corpo)
        with mock.patch.dict(os.environ, {"ADMIN_PASSWORD": "senha-antiga-do-painel"}):
            self.assertEqual(self.call("POST", "/api/login", {"senha": "senha-antiga-do-painel"})[0], 401)
        self.assertEqual(self.call("GET", "/api/eu", token="s1.9999999999.abc")[0], 401)  # sessao da senha antiga
        self.assertEqual(self.call("GET", "/api/eu", token=TOKEN)[1]["nome"], "Token da API")  # o token de scripts segue

    def test_login_por_conta(self):
        resposta = {"token": "u1.abc", "expira_em": 43200, "usuario": {"id": 1, "nome": "Ana Gestora", "perfil": "gestor"}}
        with mock.patch.object(auth, "login", return_value=resposta) as faz:
            status, corpo = self.call("POST", "/api/login", {"email": "ana@rede.org", "senha": "senha certa 2026"})
        self.assertEqual((status, corpo["token"]), (200, "u1.abc"))
        faz.assert_called_once_with("ana@rede.org", "senha certa 2026")

    def test_erros_de_login(self):
        casos = [(auth.CredenciaisInvalidas(), 401, "incorretos"), (auth.LoginBloqueado(600), 429, "minuto"),
                 (auth.ContasIndisponiveis(), 503, "migração"), (RuntimeError("x"), 503, "Tente")]
        for erro, status_esperado, trecho in casos:
            with mock.patch.object(auth, "login", side_effect=erro):
                status, corpo = self.call("POST", "/api/login", {"email": "a@x.org", "senha": "x"})
            self.assertEqual(status, status_esperado, erro)
            self.assertIn(trecho, corpo["error"])

    def test_falhas_de_login_contam_no_limite_por_ip(self):
        with mock.patch.object(auth, "login", side_effect=auth.CredenciaisInvalidas()):
            codigos = [self.call("POST", "/api/login", {"email": "a@x.org", "senha": "x"})[0] for _ in range(12)]
        self.assertEqual(codigos[:10], [401] * 10)
        self.assertIn(429, codigos[10:])


class PerfisHttpTest(ServidorBase):
    def test_conta_de_gestor_acessa_o_painel(self):
        with self.como(GESTOR), mock.patch.object(server.oferta_service, "listar", return_value=[]):
            self.assertEqual(self.call("GET", "/api/ofertas", token="u1." + "g" * 43), (200, []))

    def test_conta_de_ong_nao_acessa_o_painel(self):
        with self.como(ONG):
            for metodo, caminho in (("GET", "/api/doacoes"), ("GET", "/api/ofertas"), ("GET", "/api/usuarios"),
                                    ("GET", "/api/auditoria"), ("POST", "/api/ongs/7/link/renovar"), ("GET", "/api/indicadores")):
                status, corpo = self.call(metodo, caminho, token="u1." + "o" * 43)
                self.assertEqual(status, 403, caminho)
                self.assertIn("ONG", corpo["error"])

    def test_sessao_invalida_e_401(self):
        with self.como(None):
            for caminho in ("/api/doacoes", "/api/eu", "/api/ong-portal/matches"):
                self.assertEqual(self.call("GET", caminho, token="u1." + "x" * 43)[0], 401, caminho)

    def test_senha_provisoria_so_deixa_trocar_a_senha(self):
        provisoria = (1, "gestor", None, "Ana", "ana@rede.org", True, True, None)
        with self.como(provisoria), mock.patch.object(server.oferta_service, "listar", return_value=[]):
            status, corpo = self.call("GET", "/api/ofertas", token="u1." + "p" * 43)
            self.assertEqual((status, corpo["codigo"]), (403, "trocar_senha"))
            self.assertEqual(self.call("GET", "/api/eu", token="u1." + "p" * 43)[1]["trocar_senha"], True)
            with mock.patch.object(auth, "trocar_senha") as troca:
                self.assertEqual(self.call("POST", "/api/eu/senha", {"senha_atual": "a", "senha_nova": "b"}, token="u1." + "p" * 43)[0], 200)
                troca.assert_called_once()
                self.assertEqual(troca.call_args.args[1:], ("a", "b", "u1." + "p" * 43))

    def test_trocar_senha_com_erro_devolve_400(self):
        with self.como(GESTOR), mock.patch.object(auth, "trocar_senha", side_effect=ValueError("A senha atual está incorreta.")):
            status, corpo = self.call("POST", "/api/eu/senha", {"senha_atual": "a", "senha_nova": "b"}, token="u1." + "g" * 43)
        self.assertEqual((status, corpo["error"]), (400, "A senha atual está incorreta."))

    def test_quem_sou_eu_e_sair(self):
        with self.como(ONG):
            status, corpo = self.call("GET", "/api/eu", token="u1." + "o" * 43)
            self.assertEqual((status, corpo["perfil"], corpo["ong_nome"]), (200, "ong", "ONG Boa"))
            self.assertNotIn("hash", json.dumps(corpo))
            with mock.patch.object(auth, "logout") as sai:
                self.assertEqual(self.call("POST", "/api/logout", {}, token="u1." + "o" * 43)[0], 200)
                sai.assert_called_once_with("u1." + "o" * 43)
        self.assertEqual(self.call("GET", "/api/eu")[0], 401)
        self.assertEqual(self.call("GET", "/api/eu", token=TOKEN)[1]["nome"], "Token da API")

    def test_gestao_de_acessos_so_para_gestor(self):
        with self.como(GESTOR):
            with mock.patch.object(auth, "listar_usuarios", return_value=[{"id": 1}]):
                self.assertEqual(self.call("GET", "/api/usuarios", token="u1." + "g" * 43), (200, [{"id": 1}]))
            with mock.patch.object(auth, "criar_usuario", return_value={"id": 3, "senha_provisoria": "AbCdEfGhJkMn"}) as cria:
                status, corpo = self.call("POST", "/api/usuarios", {"perfil": "ong", "nome": "Dani", "email": "d@o.org", "ong_id": 7}, token="u1." + "g" * 43)
                self.assertEqual((status, corpo["senha_provisoria"]), (201, "AbCdEfGhJkMn"))
                cria.assert_called_once_with("ong", "Dani", "d@o.org", 7)
            with mock.patch.object(auth, "desativar") as desativa, mock.patch.object(auth, "reativar") as reativa, \
                    mock.patch.object(auth, "redefinir_senha", return_value={"id": 3, "senha_provisoria": "x"}) as redefine:
                self.assertEqual(self.call("POST", "/api/usuarios/3/desativar", {}, token="u1." + "g" * 43)[0], 200)
                self.assertEqual(desativa.call_args.args[0], 3)
                self.assertEqual(desativa.call_args.args[1]["nome"], "Ana Gestora")  # quem desativa, para a protecao da propria conta
                self.assertEqual(self.call("POST", "/api/usuarios/3/reativar", {}, token="u1." + "g" * 43)[0], 200)
                self.assertEqual(self.call("POST", "/api/usuarios/3/redefinir-senha", {}, token="u1." + "g" * 43)[1]["id"], 3)
                reativa.assert_called_once_with(3)
                redefine.assert_called_once_with(3)
            with mock.patch.object(auth, "auditoria", return_value=[]) as audita:
                self.assertEqual(self.call("GET", "/api/auditoria?limite=50", token="u1." + "g" * 43), (200, []))
                audita.assert_called_once_with("50")
        for metodo, caminho in (("GET", "/api/usuarios"), ("POST", "/api/usuarios"), ("POST", "/api/usuarios/3/desativar"), ("GET", "/api/auditoria")):
            self.assertEqual(self.call(metodo, caminho)[0], 401, caminho)

    def test_contas_indisponiveis_viram_503_com_mensagem(self):
        with self.como(GESTOR), mock.patch.object(auth, "listar_usuarios", side_effect=auth.ContasIndisponiveis()):
            status, corpo = self.call("GET", "/api/usuarios", token="u1." + "g" * 43)
        self.assertEqual(status, 503)
        self.assertIn("migração", corpo["error"])

    def test_desativar_link_da_ong(self):
        with mock.patch.object(ong_portal_service, "desativar_link", return_value={"ativo": False}) as desativa:
            self.assertEqual(self.call("POST", "/api/ongs/7/link/desativar", {}, token=TOKEN), (200, {"ativo": False}))
            desativa.assert_called_once_with(7)
        self.assertEqual(self.call("POST", "/api/ongs/7/link/desativar", {})[0], 401)


class PortalHttpTest(ServidorBase):
    ONG_TUPLA = (7, "ONG Boa", "o@o.org", None, "Santos", 100.0)

    def test_ong_entra_pela_conta_e_ve_so_o_que_e_dela(self):
        with self.como(ONG), mock.patch.object(ong_portal_service, "buscar_ong", return_value=self.ONG_TUPLA), \
                mock.patch.object(ong_portal_service.fluxo_repository, "matches_da_ong", return_value=[]) as lista:
            status, corpo = self.call("GET", "/api/ong-portal/matches", token="u1." + "o" * 43)
        self.assertEqual((status, corpo["ong"]["nome"]), (200, "ONG Boa"))
        lista.assert_called_once_with(7)  # o id da ONG vem da conta, nunca de cabecalho enviado pelo navegador

    def test_conta_nao_aceita_cabecalho_de_outra_ong(self):
        with self.como(ONG), mock.patch.object(ong_portal_service, "buscar_ong", return_value=self.ONG_TUPLA), \
                mock.patch.object(ong_portal_service.fluxo_repository, "matches_da_ong", return_value=[]) as lista:
            self.call("GET", "/api/ong-portal/matches", token="u1." + "o" * 43, cabecalhos={"X-Ong-Id": "99", "X-Ong-Codigo": "x"})
        lista.assert_called_once_with(7)

    def test_conta_de_gestor_nao_entra_no_portal_e_provisoria_so_troca_a_senha(self):
        with self.como(GESTOR):
            self.assertEqual(self.call("GET", "/api/ong-portal/matches", token="u1." + "g" * 43)[0], 401)
        provisoria = (2, "ong", 7, "Bia", "bia@ong.org", True, True, "ONG Boa")
        with self.como(provisoria):
            status, corpo = self.call("GET", "/api/ong-portal/matches", token="u1." + "o" * 43)
        self.assertEqual((status, corpo["codigo"]), (403, "trocar_senha"))

    def test_link_ativo_continua_funcionando_e_desativado_nao(self):
        from services import ong_portal_service as portal
        codigo = security.codigo_link_ong(7, 1)
        cab = {"X-Ong-Id": "7", "X-Ong-Codigo": codigo}
        with mock.patch.object(portal, "buscar_ong", return_value=self.ONG_TUPLA), \
                mock.patch.object(portal.fluxo_repository, "matches_da_ong", return_value=[]):
            with mock.patch.object(portal.fluxo_repository, "obter_info_link", return_value=(1, None, True)):
                self.assertEqual(self.call("GET", "/api/ong-portal/matches", cabecalhos=cab)[0], 200)
            with mock.patch.object(portal.fluxo_repository, "obter_info_link", return_value=(1, None, False)):
                self.assertEqual(self.call("GET", "/api/ong-portal/matches", cabecalhos=cab)[0], 401)

    def test_criar_conta_so_com_o_link_e_nunca_estando_logado(self):
        cab = {"X-Ong-Id": "7", "X-Ong-Codigo": security.codigo_link_ong(7, 1)}
        dados = {"nome": "Dani Souza", "email": "dani@ong.org", "senha": "trilha azul 7788"}
        sessao = {"token": "u1.nova", "expira_em": 43200, "usuario": {"id": 5, "perfil": "ong"}}
        with mock.patch.object(ong_portal_service, "buscar_ong", return_value=self.ONG_TUPLA), \
                mock.patch.object(ong_portal_service.fluxo_repository, "obter_info_link", return_value=(1, None, True)), \
                mock.patch.object(auth, "criar_conta_ong_pelo_link", return_value=sessao) as cria:
            status, corpo = self.call("POST", "/api/ong-portal/conta", dados, cabecalhos=cab)
            self.assertEqual((status, corpo["token"]), (201, "u1.nova"))
            self.assertEqual(cria.call_args.args[0][0], 7)
            self.assertEqual(cria.call_args.args[1:], ("Dani Souza", "dani@ong.org", "trilha azul 7788"))
        self.assertEqual(self.call("POST", "/api/ong-portal/conta", dados)[0], 401)  # sem link nem sessao
        with self.como(ONG), mock.patch.object(ong_portal_service, "buscar_ong", return_value=self.ONG_TUPLA):
            status, corpo = self.call("POST", "/api/ong-portal/conta", dados, token="u1." + "o" * 43)
            self.assertEqual(status, 400)  # quem ja tem conta nao cria outra


class CriarGestorTest(unittest.TestCase):
    """criar_gestor.py: o primeiro acesso ao painel, ja que nao existe senha unica."""

    def test_cria_gestor_com_senha_provisoria(self):
        import io
        from contextlib import redirect_stdout
        import criar_gestor
        saida = io.StringIO()
        with mock.patch.object(criar_gestor.migrar, "aplicar") as aplica, \
                mock.patch.object(criar_gestor.autenticacao_service, "criar_usuario", return_value={"id": 1, "senha_provisoria": "AbCdEfGhJkMn"}) as cria, \
                redirect_stdout(saida):
            criar_gestor.main(["criar_gestor.py", "Ana Gestora", "ana@rede.org"])
        aplica.assert_called_once_with()
        cria.assert_called_once_with("gestor", "Ana Gestora", "ana@rede.org")
        self.assertIn("AbCdEfGhJkMn", saida.getvalue())

    def test_uso_errado_e_erro_de_validacao_saem_com_mensagem(self):
        import criar_gestor
        with self.assertRaises(SystemExit) as erro:
            criar_gestor.main(["criar_gestor.py", "so-um-argumento"])
        self.assertIn("Uso", str(erro.exception))
        with mock.patch.object(criar_gestor.migrar, "aplicar"), \
                mock.patch.object(criar_gestor.autenticacao_service, "criar_usuario", side_effect=ValueError("Já existe uma conta com este e-mail.")):
            with self.assertRaises(SystemExit) as erro:
                criar_gestor.main(["criar_gestor.py", "Ana Gestora", "ana@rede.org"])
        self.assertIn("Já existe", str(erro.exception))


class AuditoriaDesligadaPorPadraoTest(unittest.TestCase):
    def test_testes_unitarios_nunca_gravam_auditoria_no_banco(self):
        self.assertFalse(server.AUDITORIA_ATIVA)  # so o __main__ liga; senao um teste com .env gravaria no banco real


class AuditoriaHttpTest(ServidorBase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(server, "AUDITORIA_ATIVA", True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def audita(self):
        return mock.patch.object(server.autenticacao_service, "registrar_auditoria")

    def test_acao_que_deu_certo_e_registrada_sem_o_corpo(self):
        with self.como(GESTOR), self.audita() as grava, mock.patch.object(server.oferta_service, "aprovar", return_value=9):
            self.assertEqual(self.call("POST", "/api/ofertas/12/aprovar", {"segredo": "nao-pode-aparecer"}, token="u1." + "g" * 43)[0], 200)
        ator, acao, recurso, registro, ip = grava.call_args.args
        self.assertEqual((ator["nome"], acao, recurso, registro), ("Ana Gestora", "POST /api/ofertas/{id}/aprovar", "ofertas", 12))
        self.assertNotIn("nao-pode-aparecer", json.dumps(grava.call_args.args, default=str))

    def test_so_registra_o_que_altera_e_funciona(self):
        with self.como(GESTOR), self.audita() as grava:
            with mock.patch.object(server.oferta_service, "listar", return_value=[]):
                self.call("GET", "/api/ofertas", token="u1." + "g" * 43)  # leitura: nao audita
            with mock.patch.object(server.oferta_service, "aprovar", side_effect=ValueError("ja foi")):
                self.assertEqual(self.call("POST", "/api/ofertas/1/aprovar", {}, token="u1." + "g" * 43)[0], 400)  # falhou: nao audita
            grava.assert_not_called()
        with self.audita() as grava:
            self.call("POST", "/api/ofertas/1/aprovar", {})  # sem credencial: nao audita
            self.call("POST", "/api/publico/doacoes", {})  # rota publica: nao audita
            grava.assert_not_called()

    def test_token_da_api_e_link_da_ong_aparecem_com_o_nome_certo(self):
        with self.audita() as grava, mock.patch.object(server.oferta_service, "recusar"):
            self.call("POST", "/api/ofertas/4/recusar", {}, token=TOKEN)
        self.assertEqual(grava.call_args.args[0]["nome"], "Token da API")
        ong = (7, "ONG Boa", "o@o.org", None, "Santos", 100.0)
        cab = {"X-Ong-Id": "7", "X-Ong-Codigo": security.codigo_link_ong(7, 1)}
        with self.audita() as grava, mock.patch.object(ong_portal_service, "buscar_ong", return_value=ong), \
                mock.patch.object(ong_portal_service.fluxo_repository, "obter_info_link", return_value=(1, None, True)), \
                mock.patch.object(ong_portal_service, "responder"):
            self.assertEqual(self.call("POST", "/api/ong-portal/matches/9/aceitar", {}, cabecalhos=cab)[0], 200)
        ator, acao, recurso, registro, _ = grava.call_args.args
        self.assertEqual((ator["nome"], acao, registro), ("Link de ONG Boa", "POST /api/ong-portal/matches/{id}/aceitar", 9))

    def test_login_bom_e_ruim_ficam_na_trilha_sem_o_email_digitado(self):
        with self.audita() as grava, mock.patch.object(auth, "login", side_effect=auth.CredenciaisInvalidas()):
            self.call("POST", "/api/login", {"email": "alguem@x.org", "senha": "minha-senha-secreta"})
        ator, acao = grava.call_args.args[:2]
        self.assertEqual((ator["nome"], acao), ("(login falhou)", "login falhou"))
        self.assertNotIn("alguem@x.org", json.dumps(grava.call_args.args, default=str))
        resposta = {"token": "u1.t", "expira_em": 1, "usuario": {"id": 1, "nome": "Ana Gestora", "perfil": "gestor"}}
        with self.audita() as grava, mock.patch.object(auth, "login", return_value=resposta):
            self.call("POST", "/api/login", {"email": "ana@rede.org", "senha": "x"})
        self.assertEqual((grava.call_args.args[0]["nome"], grava.call_args.args[1]), ("Ana Gestora", "login"))

    def test_falha_ao_gravar_nao_derruba_a_resposta(self):
        with self.como(GESTOR), mock.patch.object(server.oferta_service, "aprovar", return_value=9), \
                mock.patch.object(auth.usuario_repository, "registrar_auditoria", side_effect=RuntimeError("banco fora")), \
                self.assertLogs(level="WARNING"):
            self.assertEqual(self.call("POST", "/api/ofertas/12/aprovar", {}, token="u1." + "g" * 43)[0], 200)


if __name__ == "__main__":
    unittest.main()
