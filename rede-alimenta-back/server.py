"""API local e frontend da Rede Alimenta. Execute: python server.py."""
import json
import logging
import os
from datetime import date, datetime
from decimal import Decimal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import psycopg
import security
from services import doador_service, ong_service, doacao_service, match_service, ia_service, indicadores_service, publico_service, ong_portal_service, solicitacao_service, oferta_service, autenticacao_service
from api_docs import SWAGGER_HTML, build_openapi

ROOT = Path(__file__).resolve().parent.parent / "frontend"
SWAGGER_DIR = Path(__file__).resolve().parent / "vendor" / "swagger-ui"
SWAGGER_ASSETS = {"swagger-ui.css": "text/css", "swagger-ui-bundle.js": "text/javascript", "swagger-init.js": "text/javascript"}
SWAGGER_INIT = (
    'SwaggerUIBundle({url: "/openapi.json", dom_id: "#swagger-ui", validatorUrl: null, '
    'deepLinking: true, presets: [SwaggerUIBundle.presets.apis]});\n'
)
TRUST_PROXY = os.getenv("TRUST_PROXY") == "1"
API_TOKEN = None
REQUEST_LIMITER = security.RateLimiter(limit=300, window_seconds=60)
AUTH_FAIL_LIMITER = security.RateLimiter(limit=10, window_seconds=60)
PUBLIC_ATTEMPTS_LIMITER = security.RateLimiter(limit=40, window_seconds=3600)  # tentativas (inclusive invalidas) por IP/hora
PUBLIC_LIMITER = security.RateLimiter(limit=5, window_seconds=3600)  # ofertas aceitas por IP/hora
PUBLIC_GLOBAL_LIMITER = security.RateLimiter(limit=100, window_seconds=3600)  # ofertas por hora, no total
PUBLIC_BODY_LIMIT = 8192
ACESSO_LIMITER = security.RateLimiter(limit=3, window_seconds=3600)  # pedidos de acesso de ONG aceitos por IP/hora
ACESSO_GLOBAL_LIMITER = security.RateLimiter(limit=30, window_seconds=3600)
ACOMPANHAR_LIMITER = security.RateLimiter(limit=20, window_seconds=600)  # codigos de acompanhamento INVALIDOS por IP
AUDITORIA_ATIVA = False  # ligada ao iniciar o servidor (__main__); os testes unitarios nunca gravam no banco
ROTAS_DA_CONTA = (["api", "logout"], ["api", "eu"], ["api", "eu", "senha"])
MAX_CONNECTIONS = 64
RESOURCES = {
    "doadores": (doador_service, "doador", ["id", "nome", "email", "telefone", "regiao"]),
    "ongs": (ong_service, "ong", ["id", "nome", "email", "telefone", "regiao", "capacidade_kg", "cnpj"]),
    "doacoes": (doacao_service, "doacao", ["id", "doador_id", "doador_nome", "alimento", "categoria", "quantidade_kg", "validade", "status", "data_cadastro"]),
    "matches": (match_service, "match", ["id", "doacao_id", "alimento", "ong_id", "ong_nome", "score_ia", "prioridade", "status", "data_match"]),
}
FIELDS = {
    "doadores": ["nome", "email", "telefone", "regiao", "latitude", "longitude"],
    "ongs": ["nome", "email", "telefone", "regiao", "capacidade_kg", "latitude", "longitude", "cnpj"],
    "doacoes": ["doador_id", "alimento", "categoria", "quantidade_kg", "validade"],
    "matches": ["doacao_id", "ong_id", "score_ia", "prioridade"],
}
EDIT = {
    "doadores": ["nome", "telefone", "regiao"],
    "ongs": ["nome", "telefone", "regiao", "capacidade_kg", "cnpj"],
    "doacoes": ["alimento", "categoria", "quantidade_kg", "validade", "status"],
    "matches": ["status"],
}

def reject_constant(name):
    raise ValueError("Número inválido no JSON.")


def serialize(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError("Tipo não serializável")

class Handler(BaseHTTPRequestHandler):
    timeout = 10  # segundos por operacao de socket: mitiga conexoes lentas (slowloris)
    server_version = "RedeAlimenta"
    sys_version = ""

    def client_ip(self):
        if TRUST_PROXY:
            # O ultimo valor foi acrescentado pelo proxy confiavel; os anteriores podem ser forjados.
            forwarded = self.headers.get("X-Forwarded-For", "")
            if forwarded:
                return forwarded.split(",")[-1].strip()
        return self.client_address[0]

    def send_security_headers(self, csp=security.APP_CSP, cache="no-store"):
        for name, value in security.BASE_HEADERS.items():
            self.send_header(name, value)
        self.send_header("Content-Security-Policy", csp)
        self.send_header("Cache-Control", cache)
        if TRUST_PROXY and self.headers.get("X-Forwarded-Proto") == "https":
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

    def send_bytes(self, status, payload, content_type, csp=security.APP_CSP, extra=None):
        self._status = status
        if getattr(self, "_auditar_na_resposta", False):
            self._auditar_na_resposta = False
            try:
                self._auditar()  # antes de enviar: quem recebe a resposta ja encontra a acao registrada
            except Exception:  # noqa: BLE001 - auditar nunca pode derrubar a resposta
                logging.warning("Falha ao auditar a requisicao", exc_info=True)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_security_headers(csp)
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def respond(self, status, data, extra=None):
        payload = json.dumps(data, default=serialize, ensure_ascii=False).encode()
        self.send_bytes(status, payload, "application/json; charset=utf-8", extra=extra)

    def rate_limited(self):
        ip = self.client_ip()
        wait = max(REQUEST_LIMITER.blocked(ip), AUTH_FAIL_LIMITER.blocked(ip))
        REQUEST_LIMITER.hit(ip)
        if wait:
            self.respond(429, {"error": "Muitas requisições. Tente novamente em instantes."}, {"Retry-After": str(wait)})
        return bool(wait)

    def bearer(self):
        esquema, _, token = (self.headers.get("Authorization") or "").partition(" ")
        return token.strip() if esquema.lower() == "bearer" else ""

    def identificar(self):
        """Quem faz a requisicao, pelo cabecalho Authorization: token da API (scripts e Swagger) ou sessao de conta (u1...)."""
        token = self.bearer()
        if not token:
            return None
        if security.token_valido(self.headers.get("Authorization"), API_TOKEN):
            return autenticacao_service.ATOR_TOKEN
        try:
            return autenticacao_service.identificar(token)
        except Exception:
            logging.exception("Falha ao validar a sessao")
            return None

    def authenticated(self):
        """Rotas do gestor: conta de gestor ou token da API. Conta de ONG nao entra aqui."""
        ator = self.identificar()
        if ator and ator["perfil"] == "gestor":
            if ator["trocar_senha"]:
                self.respond(403, {"error": "Defina uma nova senha antes de continuar.", "codigo": "trocar_senha"})
                return False
            self._ator = ator
            return True
        if ator:
            self.respond(403, {"error": "Esta conta é de uma ONG e não acessa o painel do gestor."})
            return False
        ip = self.client_ip()
        AUTH_FAIL_LIMITER.hit(ip)
        logging.warning("Acesso negado à API (origem %s)", ip)
        self.respond(401, {"error": "Não autorizado."}, {"WWW-Authenticate": "Bearer"})
        return False

    def auditar_login(self, ator, acao):
        if AUDITORIA_ATIVA:
            autenticacao_service.registrar_auditoria(ator, acao, "login", None, self.client_ip())

    def _auditar(self):
        """Trilha de auditoria: quem fez qual acao que alterou algo e deu certo. Nunca guarda o corpo da requisicao."""
        if not AUDITORIA_ATIVA or self.command not in ("POST", "PUT", "DELETE") or not self._ator:
            return
        if self._status is None or not 200 <= self._status < 300:
            return
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) < 2 or parts[1] in ("login", "publico"):
            return
        acao = f"{self.command} /" + "/".join("{id}" if p.isdigit() else p for p in parts)
        registro = next((int(p) for p in parts[2:] if p.isdigit() and len(p) < 18), None)
        autenticacao_service.registrar_auditoria(self._ator, acao, parts[1], registro, self.client_ip())

    def read_json(self, max_length=65536):
        if "application/json" not in self.headers.get("Content-Type", ""):
            raise ValueError("Envie o corpo como application/json.")
        length = int(self.headers.get("Content-Length", 0))
        if not 0 < length <= max_length:
            raise ValueError("Corpo da requisição inválido.")
        data = json.loads(self.rfile.read(length), parse_constant=reject_constant)
        if not isinstance(data, dict):
            raise ValueError("Envie um objeto JSON.")
        return data

    def handle_special(self, parts):
        """Rotas de IA e indicadores. Retorna True se tratou a requisicao."""
        if self.command == "GET" and parts == ["api", "indicadores"]:
            self.respond(200, indicadores_service.calcular())
        elif self.command == "POST" and parts == ["api", "ia", "risco"]:
            self.respond(200, ia_service.classificar_lote(self.read_json()))
        elif self.command == "GET" and len(parts) == 4 and parts[1] == "doacoes" and parts[3] == "recomendacoes":
            self.respond(200, ia_service.recomendar_ongs(int(parts[2])))
        elif self.command == "POST" and len(parts) == 4 and parts[1] == "doacoes" and parts[3] in ("aprovar", "recusar"):
            (doacao_service.aprovar_doacao if parts[3] == "aprovar" else doacao_service.recusar_doacao)(int(parts[2]))
            self.respond(200, {"ok": True})
        elif self.command == "GET" and parts == ["api", "usuarios"]:
            self.respond(200, autenticacao_service.listar_usuarios())
        elif self.command == "POST" and parts == ["api", "usuarios"]:
            dados = self.read_json(4096)
            self.respond(201, autenticacao_service.criar_usuario(
                dados.get("perfil"), dados.get("nome"), dados.get("email"), dados.get("ong_id")))
        elif self.command == "POST" and len(parts) == 4 and parts[1] == "usuarios" and parts[3] in ("desativar", "reativar", "redefinir-senha"):
            if parts[3] == "desativar":
                autenticacao_service.desativar(int(parts[2]), self._ator)
                self.respond(200, {"ok": True})
            elif parts[3] == "reativar":
                autenticacao_service.reativar(int(parts[2]))
                self.respond(200, {"ok": True})
            else:
                self.respond(200, autenticacao_service.redefinir_senha(int(parts[2])))
        elif self.command == "GET" and parts == ["api", "auditoria"]:
            consulta = parse_qs(urlparse(self.path).query)
            self.respond(200, autenticacao_service.auditoria((consulta.get("limite") or ["200"])[0]))
        elif self.command == "POST" and len(parts) == 5 and parts[1] == "ongs" and parts[3:] == ["link", "desativar"]:
            self.respond(200, ong_portal_service.desativar_link(int(parts[2])))
        elif self.command == "GET" and parts == ["api", "ofertas"]:
            self.respond(200, oferta_service.listar())
        elif self.command == "POST" and len(parts) == 4 and parts[1] == "ofertas" and parts[3] in ("aprovar", "recusar"):
            if parts[3] == "aprovar":
                self.respond(200, {"ok": True, "doacao_id": oferta_service.aprovar(int(parts[2]))})
            else:
                oferta_service.recusar(int(parts[2]))
                self.respond(200, {"ok": True})
        elif self.command == "GET" and parts == ["api", "ong-solicitacoes"]:
            self.respond(200, solicitacao_service.listar())
        elif self.command == "POST" and len(parts) == 4 and parts[1] == "ong-solicitacoes" and parts[3] in ("atender", "descartar"):
            solicitacao_service.encerrar(int(parts[2]), parts[3] == "atender")
            self.respond(200, {"ok": True})
        elif self.command == "GET" and len(parts) == 4 and parts[1] == "ongs" and parts[3] == "link":
            self.respond(200, ong_portal_service.link_da_ong(int(parts[2])))
        elif self.command == "POST" and len(parts) == 5 and parts[1] == "ongs" and parts[3:] == ["link", "renovar"]:
            self.respond(200, ong_portal_service.renovar_link(int(parts[2])))
        else:
            return False
        return True

    def handle_publico(self, parts):
        """Rotas sem token: envio de oferta por qualquer pessoa. Limites por IP e no total, corpo pequeno e campo-armadilha."""
        if self.command == "POST" and parts == ["api", "publico", "ong-acesso"]:
            return self.handle_pedido_acesso()
        if self.command == "POST" and parts == ["api", "publico", "acompanhar"]:
            return self.handle_acompanhar()
        if not (self.command == "POST" and parts == ["api", "publico", "doacoes"]):
            return self.respond(404, {"error": "Rota não encontrada."})
        ip = self.client_ip()
        wait = max(PUBLIC_ATTEMPTS_LIMITER.blocked(ip), PUBLIC_LIMITER.blocked(ip), PUBLIC_GLOBAL_LIMITER.blocked("global"))
        PUBLIC_ATTEMPTS_LIMITER.hit(ip)
        if wait:
            return self.respond(429, {"error": "Muitas ofertas enviadas. Tente novamente mais tarde."}, {"Retry-After": str(wait)})
        try:
            resposta = publico_service.criar_oferta(self.read_json(PUBLIC_BODY_LIMIT))
            # So ofertas aceitas (e as descartadas pelo campo-armadilha) gastam a cota; erros de digitacao nao bloqueiam a pessoa.
            PUBLIC_LIMITER.hit(ip)
            PUBLIC_GLOBAL_LIMITER.hit("global")
            self.respond(201, resposta)
        except doacao_service.ValidacaoIndisponivel as error:
            self.respond(503, {"error": str(error)})
        except (ValueError, json.JSONDecodeError) as error:
            self.respond(400, {"error": str(error)})
        except TypeError:
            self.respond(400, {"error": "Dados em formato inválido."})
        except Exception:
            logging.exception("Falha ao receber oferta publica")
            self.respond(503, {"error": "Não foi possível registrar a oferta agora. Tente novamente em instantes."})

    def handle_acompanhar(self):
        """Em que pe esta uma oferta, pelo codigo que o doador recebeu. So tentativas com codigo invalido gastam a cota."""
        if self.rate_limited():
            return
        ip = self.client_ip()
        wait = ACOMPANHAR_LIMITER.blocked(ip)
        if wait:
            return self.respond(429, {"error": "Muitas tentativas. Tente novamente em instantes."}, {"Retry-After": str(wait)})
        try:
            self.respond(200, publico_service.acompanhar(self.read_json(1024).get("codigo")))
        except publico_service.CodigoInvalido:
            ACOMPANHAR_LIMITER.hit(ip)
            self.respond(404, {"error": "Código não encontrado. Confira se copiou o código inteiro."})
        except (ValueError, json.JSONDecodeError) as error:
            self.respond(400, {"error": str(error)})
        except Exception:
            logging.exception("Falha ao consultar o acompanhamento da oferta")
            self.respond(503, {"error": "Não foi possível consultar agora. Tente novamente em instantes."})

    def handle_pedido_acesso(self):
        """Pedido de acesso ao portal feito por uma ONG (sem token). Mesmos cuidados da oferta publica, com cota propria."""
        ip = self.client_ip()
        wait = max(PUBLIC_ATTEMPTS_LIMITER.blocked(ip), ACESSO_LIMITER.blocked(ip), ACESSO_GLOBAL_LIMITER.blocked("global"))
        PUBLIC_ATTEMPTS_LIMITER.hit(ip)
        if wait:
            return self.respond(429, {"error": "Muitos pedidos enviados. Tente novamente mais tarde."}, {"Retry-After": str(wait)})
        try:
            resposta = solicitacao_service.criar_pedido(self.read_json(PUBLIC_BODY_LIMIT))
            ACESSO_LIMITER.hit(ip)
            ACESSO_GLOBAL_LIMITER.hit("global")
            self.respond(201, resposta)
        except (ValueError, json.JSONDecodeError) as error:
            self.respond(400, {"error": str(error)})
        except TypeError:
            self.respond(400, {"error": "Dados em formato inválido."})
        except Exception:
            logging.exception("Falha ao receber pedido de acesso")
            self.respond(503, {"error": "Não foi possível registrar o pedido agora. Tente novamente em instantes."})

    def handle_portal_ong(self, parts):
        """Rotas da ONG: por conta (sessao Bearer u1...) ou, enquanto o link estiver ativo, pelo link com codigo."""
        ip = self.client_ip()
        try:
            if self.bearer().startswith(security.PREFIXO_SESSAO_USUARIO):
                ator = autenticacao_service.identificar(self.bearer())
                if not ator or ator["perfil"] != "ong":
                    raise ong_portal_service.AcessoNegado()
                if ator["trocar_senha"]:
                    return self.respond(403, {"error": "Defina uma nova senha antes de continuar.", "codigo": "trocar_senha"})
                ong = ong_portal_service.ong_da_conta(ator)
            else:
                ong = ong_portal_service.autenticar(
                    int(self.headers.get("X-Ong-Id", "0") or 0), self.headers.get("X-Ong-Codigo", "")
                )
                ator = autenticacao_service.ator_do_link(ong)
        except (ong_portal_service.AcessoNegado, ValueError):
            AUTH_FAIL_LIMITER.hit(ip)
            logging.warning("Acesso negado ao portal da ONG (origem %s)", ip)
            return self.respond(401, {"error": "Acesso inválido ou expirado. Entre com e-mail e senha ou peça um novo link ao administrador."})
        except Exception:
            logging.exception("Falha ao validar o acesso da ONG")
            return self.respond(503, {"error": "Não foi possível acessar os dados agora."})
        self._ator = ator
        try:
            if self.command == "GET" and parts == ["api", "ong-portal", "matches"]:
                self.respond(200, ong_portal_service.painel(ong))
            elif self.command == "POST" and len(parts) == 5 and parts[2] == "matches" and parts[3].isdigit() \
                    and parts[4] in ("aceitar", "recusar", "receber"):
                if parts[4] == "receber":
                    ong_portal_service.confirmar_recebimento(ong, int(parts[3]))
                else:
                    ong_portal_service.responder(ong, int(parts[3]), parts[4] == "aceitar")
                self.respond(200, {"ok": True})
            elif self.command == "POST" and parts == ["api", "ong-portal", "conta"]:
                if ator["tipo"] != "link":
                    return self.respond(400, {"error": "Você já está com a sua conta."})
                dados = self.read_json(4096)
                self.respond(201, autenticacao_service.criar_conta_ong_pelo_link(
                    ong, dados.get("nome"), dados.get("email"), dados.get("senha")))
            else:
                self.respond(404, {"error": "Rota não encontrada."})
        except autenticacao_service.ContasIndisponiveis:
            self.respond(503, {"error": "Contas individuais indisponíveis: o banco ainda não tem a migração. Use o link."})
        except (ValueError, json.JSONDecodeError) as error:
            self.respond(400, {"error": str(error)})
        except Exception:
            logging.exception("Falha no portal da ONG")
            self.respond(503, {"error": "Não foi possível concluir a operação agora."})

    def handle_login(self):
        """Login por e-mail e senha de uma conta. Falhas contam no limite por IP."""
        ip = self.client_ip()
        if self.rate_limited():
            return
        try:
            dados = self.read_json(2048)
        except (ValueError, json.JSONDecodeError) as error:
            return self.respond(400, {"error": str(error)})
        email, senha = dados.get("email"), dados.get("senha")
        try:
            resposta = autenticacao_service.login(email, senha)
        except autenticacao_service.CredenciaisInvalidas:
            AUTH_FAIL_LIMITER.hit(ip)
            logging.warning("Login recusado (origem %s)", ip)
            self.auditar_login({"tipo": "sistema", "id": None, "nome": "(login falhou)"}, "login falhou")
            return self.respond(401, {"error": "E-mail ou senha incorretos."})
        except autenticacao_service.LoginBloqueado as bloqueio:
            return self.respond(429, {"error": "Muitas tentativas com este e-mail. Tente de novo em %d minuto(s)." % (bloqueio.segundos // 60 + 1)},
                                {"Retry-After": str(bloqueio.segundos)})
        except autenticacao_service.ContasIndisponiveis:
            return self.respond(503, {"error": "Contas individuais indisponíveis: o banco ainda não tem a migração 007. Reinicie o servidor (ele aplica as migrações) ou rode python migrar.py."})
        except Exception:
            logging.exception("Falha no login")
            return self.respond(503, {"error": "Não foi possível entrar agora. Tente novamente em instantes."})
        usuario = resposta["usuario"]
        self.auditar_login({"tipo": "usuario", "id": usuario["id"], "nome": usuario["nome"]}, "login")
        self.respond(200, resposta)

    def handle_conta(self, parts):
        """Rotas da propria conta (qualquer perfil): quem sou, sair e trocar a senha."""
        ator = self.identificar()
        if not ator:
            AUTH_FAIL_LIMITER.hit(self.client_ip())
            return self.respond(401, {"error": "Não autorizado."}, {"WWW-Authenticate": "Bearer"})
        self._ator = ator
        try:
            if self.command == "GET" and parts == ["api", "eu"]:
                self.respond(200, autenticacao_service.usuario_publico(ator))
            elif self.command == "POST" and parts == ["api", "logout"]:
                autenticacao_service.logout(self.bearer())
                self.respond(200, {"ok": True})
            elif self.command == "POST" and parts == ["api", "eu", "senha"]:
                dados = self.read_json(2048)
                autenticacao_service.trocar_senha(ator, dados.get("senha_atual"), dados.get("senha_nova"), self.bearer())
                self.respond(200, {"ok": True})
            else:
                self.respond(404, {"error": "Rota não encontrada."})
        except (ValueError, json.JSONDecodeError) as error:
            self.respond(400, {"error": str(error)})
        except Exception:
            logging.exception("Falha na conta")
            self.respond(503, {"error": "Não foi possível concluir a operação agora."})

    def handle_api(self):
        self._ator, self._status, self._auditar_na_resposta = None, None, True
        self._despachar_api()

    def _despachar_api(self):
        parts = urlparse(self.path).path.strip("/").split("/")
        if self.command == "POST" and parts == ["api", "login"]:
            return self.handle_login()
        if len(parts) >= 2 and parts[1] == "publico":
            return self.handle_publico(parts)
        if len(parts) >= 2 and parts[1] == "ong-portal":
            if self.rate_limited():
                return
            return self.handle_portal_ong(parts)
        if parts in ROTAS_DA_CONTA:
            if self.rate_limited():
                return
            return self.handle_conta(parts)
        if self.rate_limited() or not self.authenticated():
            return
        try:
            if self.handle_special(parts):
                return
        except autenticacao_service.ContasIndisponiveis:
            return self.respond(503, {"error": "Contas individuais indisponíveis: o banco ainda não tem a migração 007."})
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            return self.respond(400, {"error": str(error)})
        except Exception:
            logging.exception("Falha na operação")
            return self.respond(503, {"error": "Não foi possível acessar os dados. Verifique o banco e DATABASE_URL."})
        if len(parts) not in (2, 3) or parts[1] not in RESOURCES:
            return self.respond(404, {"error": "Rota não encontrada."})
        resource = parts[1]
        module, singular, columns = RESOURCES[resource]
        try:
            record_id = int(parts[2]) if len(parts) == 3 else None
            if self.command == "GET" and record_id is None:
                rows = getattr(module, "obter_" + resource)()
                return self.respond(200, [dict(zip(columns, row)) for row in rows])
            if self.command == "DELETE" and record_id is not None:
                getattr(module, "remover_" + singular)(record_id)
                return self.respond(200, {"ok": True})
            if self.command not in ("POST", "PUT"):
                return self.respond(405, {"error": "Operação não suportada."})
            data = self.read_json()
            fields = FIELDS[resource] if self.command == "POST" else EDIT[resource]
            optional = {"latitude", "longitude", "telefone", "cnpj"}
            kwargs = {}
            for field in fields:
                if field == "cnpj" and field not in data:
                    continue  # CNPJ ausente: na criacao fica sem CNPJ; na edicao, mantem o atual
                if field not in data and field not in optional:
                    raise ValueError("Campo obrigatório: " + field)
                kwargs[field] = data.get(field)
            if self.command == "POST" and record_id is None:
                new_id = getattr(module, "criar_" + singular)(**kwargs)
                return self.respond(201, {"id": new_id})
            if self.command == "PUT" and record_id is not None:
                function = module.alterar_status_match if resource == "matches" else getattr(module, "editar_" + singular)
                function(record_id, **kwargs)
                return self.respond(200, {"ok": True})
            return self.respond(405, {"error": "Operação não suportada."})
        except doacao_service.ValidacaoIndisponivel as error:
            self.respond(503, {"error": str(error)})
        except (ValueError, json.JSONDecodeError) as error:
            self.respond(400, {"error": str(error)})
        except TypeError:
            self.respond(400, {"error": "Dados em formato inválido."})
        except psycopg.errors.UniqueViolation as error:
            cnpj_repetido = "cnpj" in (error.diag.constraint_name or "")
            self.respond(409, {"error": "Já existe uma ONG com este CNPJ." if cnpj_repetido else "Já existe um cadastro com este e-mail."})
        except psycopg.errors.ForeignKeyViolation:
            if self.command == "DELETE":
                self.respond(409, {"error": "Não é possível excluir: há registros vinculados a este item."})
            else:
                self.respond(400, {"error": "O registro relacionado não existe mais. Atualize a página."})
        except (psycopg.errors.DataError, psycopg.errors.IntegrityError):
            logging.exception("Dados rejeitados pelo banco")
            self.respond(400, {"error": "Dados inválidos. Revise os valores informados."})
        except Exception:
            logging.exception("Falha na operação")
            self.respond(503, {"error": "Não foi possível acessar os dados. Verifique o banco e DATABASE_URL."})

    def do_GET(self):
        route = urlparse(self.path).path
        if route.startswith("/api/"):
            return self.handle_api()
        if self.rate_limited():
            return
        if route == "/health":
            return self.respond(200, {"status": "ok"})
        if route == "/openapi.json":
            return self.respond(200, build_openapi(FIELDS, EDIT, RESOURCES))
        if route in ("/docs", "/docs/"):
            return self.send_bytes(200, SWAGGER_HTML.encode("utf-8"), "text/html; charset=utf-8", security.DOCS_CSP)
        if route.startswith("/docs/assets/"):
            name = route.rsplit("/", 1)[-1]
            if name not in SWAGGER_ASSETS:
                return self.respond(404, {"error": "Página não encontrada."})
            payload = SWAGGER_INIT.encode() if name == "swagger-init.js" else (SWAGGER_DIR / name).read_bytes()
            return self.send_bytes(200, payload, SWAGGER_ASSETS[name] + "; charset=utf-8", security.DOCS_CSP)
        assets = {
            "/": ("inicio.html", "text/html"), "/privacidade": ("privacidade.html", "text/html"), "/admin": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
            "/indicadores.js": ("indicadores.js", "text/javascript"), "/style.css": ("style.css", "text/css"),
            "/doar": ("doar.html", "text/html"), "/doar.js": ("doar.js", "text/javascript"),
            "/ong": ("ong.html", "text/html"), "/ong.js": ("ong.js", "text/javascript"),
            "/acompanhar": ("acompanhar.html", "text/html"), "/acompanhar.js": ("acompanhar.js", "text/javascript"),
        }
        if route not in assets:
            return self.respond(404, {"error": "Página não encontrada."})
        filename, mime = assets[route]
        self.send_bytes(200, (ROOT / filename).read_bytes(), mime + "; charset=utf-8")

    do_POST = handle_api
    do_PUT = handle_api
    do_DELETE = handle_api

class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Limita conexoes simultaneas para evitar esgotamento de threads."""
    daemon_threads = True
    request_queue_size = 64

    def __init__(self, *args, **kwargs):
        self._slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


def make_server(host, port):
    global API_TOKEN
    API_TOKEN = security.load_api_token()
    return BoundedThreadingHTTPServer((host, port), Handler)


def migrar_banco():
    """Aplica o esquema e as migracoes (aditivas e idempotentes) ao iniciar, para nao depender de lembrar do migrar.py.

    Se o banco estiver fora do ar ou sem permissao de DDL, o servidor sobe mesmo assim: os recursos novos avisam que faltam."""
    if os.getenv("AUTO_MIGRAR", "1") == "0":
        return
    try:
        import migrar  # noqa: PLC0415 - so no inicio do servidor, nunca nos testes
        logging.info("Banco atualizado: %s", ", ".join(migrar.aplicar()))
    except Exception:
        logging.exception("Não foi possível aplicar as migrações do banco; o servidor segue sem elas.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    AUDITORIA_ATIVA = True
    migrar_banco()
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    server = make_server(host, port)
    print(f"Rede Alimenta: http://localhost:{port}")
    print(f"Swagger: http://localhost:{port}/docs")
    server.serve_forever()
