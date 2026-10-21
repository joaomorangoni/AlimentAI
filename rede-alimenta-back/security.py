"""Controles de seguranca da API: token Bearer, limite de taxa e cabecalhos."""
import base64
import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import deque

MIN_TOKEN_LENGTH = 32
PLACEHOLDER_TOKENS = {"troque-por-um-token-aleatorio-com-32-ou-mais-caracteres"}

APP_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
    "frame-ancestors 'none'"
)
# Swagger UI aplica estilos inline em tempo de execucao; scripts continuam restritos a 'self'.
DOCS_CSP = APP_CSP.replace("style-src 'self'", "style-src 'self' 'unsafe-inline'")

BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def load_api_token():
    """Le API_TOKEN do ambiente. Falha fechada: sem token forte, o servidor nao inicia."""
    token = os.getenv("API_TOKEN", "")
    if len(token) < MIN_TOKEN_LENGTH or token in PLACEHOLDER_TOKENS:
        raise RuntimeError(
            "API_TOKEN ausente, de exemplo ou com menos de %d caracteres. "
            "Gere um com: python -c \"import secrets; print(secrets.token_urlsafe(32))\"" % MIN_TOKEN_LENGTH
        )
    return token


def segredo_links_ong():
    """Segredo que assina os links das ONGs: ONG_LINK_SECRET, ou derivado do API_TOKEN (nunca o proprio token)."""
    segredo = os.getenv("ONG_LINK_SECRET", "")
    if len(segredo) >= MIN_TOKEN_LENGTH:
        return segredo.encode()
    return hmac.new(load_api_token().encode(), b"rede-alimenta/ong-link/v1", hashlib.sha256).digest()


def codigo_link_ong(ong_id, versao):
    """Codigo (160 bits) do link de uma ONG. Trocar a versao invalida o link anterior."""
    assinatura = hmac.new(segredo_links_ong(), f"ong:{ong_id}:{versao}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(assinatura[:20]).decode().rstrip("=")


def codigo_link_valido(informado, ong_id, versao):
    return hmac.compare_digest(str(informado or "").encode(), codigo_link_ong(ong_id, versao).encode())


def token_valido(authorization_header, expected_token):
    """Compara o cabecalho 'Authorization: Bearer <token>' em tempo constante."""
    scheme, _, supplied = (authorization_header or "").partition(" ")
    if scheme.lower() != "bearer":
        supplied = ""
    return hmac.compare_digest(supplied.strip().encode(), expected_token.encode())


# --- Contas individuais: senha com PBKDF2 e sessoes aleatorias guardadas so como hash -----------------------------------
ITERACOES_SENHA = 600_000  # recomendacao OWASP para PBKDF2-HMAC-SHA256; o valor fica gravado em cada hash (da para subir depois)
PREFIXO_SESSAO_USUARIO = "u1."
SENHA_MINIMA, SENHA_MAXIMA = 10, 128
_SENHAS_COMUNS = {
    "1234567890", "12345678910", "0123456789", "senha12345", "senha123456", "password123", "password1234", "qwertyuiop",
    "1q2w3e4r5t", "abcdefghij", "alimenta123", "alimenta1234", "redealimenta", "mudar12345", "trocar12345",
}
_hash_falso = []


def hash_senha(senha):
    """'pbkdf2_sha256$iteracoes$sal$hash' (base64). Sal aleatorio de 16 bytes por senha."""
    sal = secrets.token_bytes(16)
    derivado = hashlib.pbkdf2_hmac("sha256", senha.encode(), sal, ITERACOES_SENHA)
    return "pbkdf2_sha256$%d$%s$%s" % (
        ITERACOES_SENHA, base64.b64encode(sal).decode(), base64.b64encode(derivado).decode()
    )


def verificar_senha(senha, armazenado):
    """Compara em tempo constante. Hash mal formado ou senha que nao e texto nunca levantam erro: so devolvem False."""
    try:
        algoritmo, iteracoes, sal, esperado = str(armazenado).split("$")
        if algoritmo != "pbkdf2_sha256" or not isinstance(senha, str):
            return False
        derivado = hashlib.pbkdf2_hmac("sha256", senha.encode(), base64.b64decode(sal), int(iteracoes))
        return hmac.compare_digest(derivado, base64.b64decode(esperado))
    except (ValueError, TypeError):
        return False


def hash_falso():
    """Hash de uma senha que ninguem tem: confere-se contra ele quando o e-mail nao existe, para nao revelar pelo tempo de resposta."""
    if not _hash_falso:
        _hash_falso.append(hash_senha(secrets.token_urlsafe(16)))
    return _hash_falso[0]


def problema_na_senha(senha, email="", nome=""):
    """Texto do problema se a senha nao serve como senha nova; None se serve."""
    if not isinstance(senha, str):
        return "A senha deve ser um texto."
    if not SENHA_MINIMA <= len(senha) <= SENHA_MAXIMA:
        return "A senha deve ter de %d a %d caracteres." % (SENHA_MINIMA, SENHA_MAXIMA)
    if senha.isdigit() or len(set(senha)) < 4:
        return "Escolha uma senha menos previsível (não só números nem poucos caracteres repetidos)."
    minuscula = senha.lower()
    if minuscula in _SENHAS_COMUNS:
        return "Essa senha é muito comum. Escolha outra."
    local = str(email).split("@")[0].lower()
    if len(local) >= 4 and local in minuscula:
        return "A senha não pode conter o seu e-mail."
    primeiro_nome = str(nome).split(" ")[0].lower()
    if len(primeiro_nome) >= 4 and minuscula.startswith(primeiro_nome):
        return "A senha não pode começar com o seu nome."
    return None


def senha_provisoria():
    """12 caracteres sem letras parecidas (0/O, 1/l/I), para ditar ou digitar sem erro. Aparece uma unica vez."""
    alfabeto = "abcdefghijkmnpqrstuvwxyzACDEFGHJKLMNPQRTUVWXYZ234679"
    return "".join(secrets.choice(alfabeto) for _ in range(12))


def novo_token_sessao():
    """(token, hash): o token vai para o navegador; o banco guarda so o hash SHA-256."""
    token = PREFIXO_SESSAO_USUARIO + secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token):
    return hashlib.sha256(str(token).encode()).hexdigest()


class RateLimiter:
    """Janela deslizante em memoria, por chave (IP). Adequado para uma instancia."""

    def __init__(self, limit, window_seconds, max_keys=10000):
        self.limit, self.window, self.max_keys = limit, window_seconds, max_keys
        self._hits = {}
        self._lock = threading.Lock()

    def _prune(self, hits, now):
        while hits and now - hits[0] > self.window:
            hits.popleft()

    def blocked(self, key):
        """Retorna segundos para tentar de novo se a chave estourou o limite; senao 0."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                return 0
            self._prune(hits, now)
            if len(hits) >= self.limit:
                return int(self.window - (now - hits[0])) + 1
            return 0

    def hit(self, key):
        now = time.monotonic()
        with self._lock:
            if key not in self._hits and len(self._hits) >= self.max_keys:
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                    del self._hits[k]
                if len(self._hits) >= self.max_keys:
                    self._hits.pop(next(iter(self._hits)))
            hits = self._hits.setdefault(key, deque())
            self._prune(hits, now)
            hits.append(now)
