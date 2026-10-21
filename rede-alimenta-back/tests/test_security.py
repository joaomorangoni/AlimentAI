"""Testes dos controles de seguranca. Nao acessam o banco. Execute: python -m unittest discover -s tests"""
import http.client
import json
import os
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TOKEN = "t" * 40
os.environ["API_TOKEN"] = TOKEN

import security  # noqa: E402
import server  # noqa: E402


class SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.make_server("127.0.0.1", 0)
        server.API_TOKEN = TOKEN  # cada modulo de teste usa o proprio token
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        server.REQUEST_LIMITER = security.RateLimiter(300, 60)
        server.AUTH_FAIL_LIMITER = security.RateLimiter(10, 60)

    def get(self, path, headers=None, method="GET"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request(method, path, headers=headers or {})
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp, body

    def test_api_sem_token_retorna_401(self):
        for path in ("/api/doadores", "/api/ongs", "/api/doacoes", "/api/matches"):
            resp, _ = self.get(path)
            self.assertEqual(resp.status, 401, path)
            self.assertEqual(resp.getheader("WWW-Authenticate"), "Bearer")

    def test_escrita_sem_token_retorna_401(self):
        for method in ("POST", "PUT", "DELETE"):
            resp, _ = self.get("/api/doadores/1", method=method)
            self.assertEqual(resp.status, 401, method)

    def test_token_errado_e_esquema_errado(self):
        for value in ("Bearer errado", "Basic " + TOKEN, TOKEN, "Bearer", ""):
            resp, _ = self.get("/api/doadores", {"Authorization": value})
            self.assertEqual(resp.status, 401, value)

    def test_token_correto_passa_da_autenticacao(self):
        resp, _ = self.get("/api/rota-inexistente", {"Authorization": "Bearer " + TOKEN})
        self.assertEqual(resp.status, 404)

    def test_forca_bruta_e_bloqueada(self):
        statuses = [self.get("/api/doadores", {"Authorization": "Bearer x"})[0].status for _ in range(12)]
        self.assertIn(429, statuses)
        resp, _ = self.get("/api/doadores", {"Authorization": "Bearer " + TOKEN})
        self.assertEqual(resp.status, 429)
        self.assertTrue(resp.getheader("Retry-After"))

    def test_limite_geral_de_requisicoes(self):
        server.REQUEST_LIMITER = security.RateLimiter(5, 60)
        statuses = [self.get("/health")[0].status for _ in range(8)]
        self.assertEqual(statuses[:5], [200] * 5)
        self.assertIn(429, statuses)

    def test_cabecalhos_de_seguranca(self):
        for path in ("/", "/health", "/docs", "/api/doadores"):
            resp, _ = self.get(path)
            for name in ("X-Content-Type-Options", "X-Frame-Options", "Content-Security-Policy", "Referrer-Policy"):
                self.assertIsNotNone(resp.getheader(name), path + " sem " + name)
            self.assertEqual(resp.getheader("Cache-Control"), "no-store")
            self.assertNotIn("Python", resp.getheader("Server", ""))
        resp, _ = self.get("/")
        self.assertIn("script-src 'self'", resp.getheader("Content-Security-Policy"))
        self.assertNotIn("unsafe-inline", resp.getheader("Content-Security-Policy"))

    def test_swagger_local_sem_recursos_externos(self):
        resp, body = self.get("/docs")
        self.assertEqual(resp.status, 200)
        self.assertNotIn(b"unpkg", body)
        self.assertNotIn(b"http://", body)
        for name in ("swagger-ui.css", "swagger-ui-bundle.js", "swagger-init.js"):
            resp, _ = self.get("/docs/assets/" + name)
            self.assertEqual(resp.status, 200, name)
        resp, _ = self.get("/docs/assets/../server.py")
        self.assertEqual(resp.status, 404)
        resp, _ = self.get("/docs/assets/server.py")
        self.assertEqual(resp.status, 404)

    def test_openapi_declara_bearer(self):
        _, body = self.get("/openapi.json")
        spec = json.loads(body)
        self.assertEqual(spec["components"]["securitySchemes"]["bearerAuth"]["scheme"], "bearer")

    def login(self, senha, email=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        corpo = {"senha": senha} if email is None else {"email": email, "senha": senha}
        conn.request("POST", "/api/login", json.dumps(corpo), {"Content-Type": "application/json"})
        resp = conn.getresponse()
        body = json.loads(resp.read())
        conn.close()
        return resp, body

    def test_nao_ha_senha_unica_de_painel(self):
        """O API_TOKEN e o ADMIN_PASSWORD antigo nao entram mais no painel: o login e so por conta (e-mail e senha)."""
        with mock.patch.dict(os.environ, {"ADMIN_PASSWORD": "uma-senha-qualquer-de-painel"}):
            for senha in (TOKEN, "uma-senha-qualquer-de-painel"):
                resp, body = self.login(senha)
                self.assertEqual(resp.status, 401, senha)
                self.assertNotIn("token", body)
                resp, _ = self.login(senha, email="")
                self.assertEqual(resp.status, 401)
        self.assertFalse(hasattr(security, "senha_valida") or hasattr(security, "criar_sessao"))

    def test_sessao_antiga_da_senha_unica_e_recusada(self):
        for token in ("s1.9999999999.abc", "s1.1.2"):
            resp, _ = self.get("/api/doadores", {"Authorization": "Bearer " + token})
            self.assertEqual(resp.status, 401)

    def test_login_errado_repetido_e_limitado(self):
        for _ in range(10):
            self.login("errada")
        resp, _ = self.login("outra errada")
        self.assertEqual(resp.status, 429)

    def test_servidor_nao_inicia_sem_token_forte(self):
        original = os.environ["API_TOKEN"]
        try:
            for bad in ("", "curto", next(iter(security.PLACEHOLDER_TOKENS))):
                os.environ["API_TOKEN"] = bad
                with self.assertRaises(RuntimeError):
                    security.load_api_token()
        finally:
            os.environ["API_TOKEN"] = original

    def test_rate_limiter_janela(self):
        limiter = security.RateLimiter(2, 60)
        limiter.hit("a")
        self.assertEqual(limiter.blocked("a"), 0)
        limiter.hit("a")
        self.assertGreater(limiter.blocked("a"), 0)
        self.assertEqual(limiter.blocked("b"), 0)

    def test_paginas_publicas_sao_servidas_com_csp(self):
        for path in ("/", "/doar", "/ong", "/privacidade", "/admin"):
            resp, body = self.get(path)
            self.assertEqual(resp.status, 200, path)
            self.assertIn("default-src", resp.getheader("Content-Security-Policy") or "", path)
            self.assertNotIn(b"<script>", body, path)  # a CSP proibe script inline

    def test_frontend_nao_usa_estilo_nem_script_inline(self):
        """A CSP (style-src 'self', script-src 'self') bloqueia style="..." e scripts inline: quebraria so no navegador."""
        raiz = Path(__file__).resolve().parents[2] / "frontend"
        arquivos = [*raiz.glob("*.html"), *raiz.glob("*.js")]
        self.assertGreaterEqual(len(arquivos), 10)
        for arquivo in arquivos:
            texto = arquivo.read_text(encoding="utf-8")
            self.assertNotRegex(texto, r"\sstyle\s*=", arquivo.name)
            self.assertNotRegex(texto, r"\.style\.(?!removeProperty)\w+\s*=", arquivo.name)  # element.style.x = ... tambem e bloqueado
            if arquivo.suffix == ".html":
                self.assertNotRegex(texto, r"<script(?![^>]*\bsrc=)[^>]*>", arquivo.name)
                self.assertNotRegex(texto, r"\son\w+\s*=", arquivo.name)  # onclick= e afins

    def test_rotas_do_gestor_para_pedidos_de_acesso_exigem_token(self):
        for method, path in (("GET", "/api/ong-solicitacoes"), ("POST", "/api/ong-solicitacoes/1/atender"),
                             ("POST", "/api/ong-solicitacoes/1/descartar")):
            resp, _ = self.get(path, method=method)
            self.assertEqual(resp.status, 401, path)

    def test_pedido_de_acesso_publico_tem_cota_propria(self):
        server.PUBLIC_ATTEMPTS_LIMITER = security.RateLimiter(40, 3600)
        server.ACESSO_LIMITER = security.RateLimiter(3, 3600)
        server.ACESSO_GLOBAL_LIMITER = security.RateLimiter(30, 3600)
        corpo = json.dumps({"nome": "ONG Boa", "email": "o@boa.org", "regiao": "Santos", "aceite": True})
        statuses = []
        with mock.patch.object(server.solicitacao_service, "criar_pedido", return_value={"mensagem": "ok"}):
            for _ in range(5):
                conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
                conn.request("POST", "/api/publico/ong-acesso", body=corpo, headers={"Content-Type": "application/json"})
                statuses.append(conn.getresponse().status)
                conn.close()
        self.assertEqual(statuses[:3], [201] * 3)
        self.assertEqual(statuses[3:], [429, 429])


if __name__ == "__main__":
    unittest.main()
