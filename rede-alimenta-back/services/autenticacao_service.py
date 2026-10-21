"""Contas individuais (gestor e ONG): login por e-mail e senha, sessoes, troca e redefinicao de senha, acessos e auditoria.

O token da API (scripts e Swagger) continua existindo, mas nao e uma conta: as acoes feitas por ele aparecem na auditoria
como "Token da API". Nao ha senha unica de painel: sem conta de gestor, o primeiro gestor se cria com criar_gestor.py."""
import logging

import psycopg

import security
from repositories import usuario_repository
from repositories.ong_repository import buscar_ong
from services import validacao

SESSAO_SEGUNDOS = 12 * 3600
MAX_CONTAS_ONG = 10
PERFIS = ("gestor", "ong")
LOGIN_LIMITER = security.RateLimiter(limit=5, window_seconds=900)  # falhas por e-mail digitado (exista ele ou nao)


class CredenciaisInvalidas(Exception):
    """E-mail ou senha errados, conta desativada ou inexistente: sempre a mesma resposta."""


class LoginBloqueado(Exception):
    def __init__(self, segundos):
        super().__init__(segundos)
        self.segundos = segundos


class ContasIndisponiveis(Exception):
    """Banco sem a migracao 007: as contas ainda nao existem."""


def _publico(linha):
    return {"id": linha[0], "perfil": linha[1], "ong_id": linha[2], "nome": linha[3], "email": linha[4],
            "trocar_senha": linha[6], "ong_nome": linha[7]}


def _ator(linha):
    return {"tipo": "usuario", "id": linha[0], "perfil": linha[1], "ong_id": linha[2], "nome": linha[3],
            "email": linha[4], "trocar_senha": linha[6], "ong_nome": linha[7]}


ATOR_TOKEN = {"tipo": "token", "id": None, "perfil": "gestor", "ong_id": None, "nome": "Token da API", "email": "",
              "trocar_senha": False, "ong_nome": None}


def ator_do_link(ong):
    return {"tipo": "link", "id": ong[0], "perfil": "ong", "ong_id": ong[0], "nome": f"Link de {ong[1]}", "email": "",
            "trocar_senha": False, "ong_nome": ong[1]}


def usuario_publico(ator):
    """O que o navegador pode saber de quem esta logado (nunca o hash)."""
    return {"id": ator["id"], "perfil": ator["perfil"], "ong_id": ator["ong_id"], "nome": ator["nome"],
            "email": ator["email"], "trocar_senha": ator["trocar_senha"], "ong_nome": ator["ong_nome"],
            "tipo": ator["tipo"]}


def _abrir_sessao(linha):
    token, hash_do_token = security.novo_token_sessao()
    usuario_repository.criar_sessao(linha[0], hash_do_token, SESSAO_SEGUNDOS)
    usuario_repository.registrar_acesso(linha[0])
    return {"token": token, "expira_em": SESSAO_SEGUNDOS, "usuario": _publico(linha)}


def login(email, senha):
    """Entra com e-mail e senha. Erro e demora iguais para e-mail inexistente, senha errada e conta desativada."""
    if not isinstance(email, str) or not isinstance(senha, str) or not email.strip() or len(email) > 160 or len(senha) > 200:
        raise CredenciaisInvalidas()

    chave = email.strip().lower()
    espera = LOGIN_LIMITER.blocked(chave)

    if espera:
        raise LoginBloqueado(espera)

    try:
        linha = usuario_repository.buscar_para_login(chave)
    except psycopg.errors.UndefinedTable:
        raise ContasIndisponiveis() from None

    confere = security.verificar_senha(senha, linha[8] if linha else security.hash_falso())

    if not (linha and confere and linha[5]):
        LOGIN_LIMITER.hit(chave)
        raise CredenciaisInvalidas()

    return _abrir_sessao(linha)


def identificar(token):
    """Ator da sessao de um usuario (token 'u1....'), ou None se a sessao nao existe, venceu ou a conta foi desativada."""
    if not isinstance(token, str) or not token.startswith(security.PREFIXO_SESSAO_USUARIO) or len(token) > 100:
        return None

    try:
        linha = usuario_repository.buscar_sessao(security.hash_token(token))
    except psycopg.errors.UndefinedTable:
        return None

    return _ator(linha) if linha and linha[5] else None


def logout(token):
    if isinstance(token, str) and token.startswith(security.PREFIXO_SESSAO_USUARIO):
        usuario_repository.apagar_sessao(security.hash_token(token))


def trocar_senha(ator, senha_atual, senha_nova, token):
    if ator["tipo"] != "usuario":
        raise ValueError("O token da API não é uma conta: ele é definido no servidor (API_TOKEN).")

    chave = f"troca:{ator['id']}"

    if LOGIN_LIMITER.blocked(chave):
        raise ValueError("Muitas tentativas. Aguarde alguns minutos.")

    atual = usuario_repository.senha_hash_de(ator["id"])

    if not atual or not security.verificar_senha(senha_atual, atual):
        LOGIN_LIMITER.hit(chave)
        raise ValueError("A senha atual está incorreta.")

    problema = security.problema_na_senha(senha_nova, ator["email"], ator["nome"])

    if problema:
        raise ValueError(problema)

    if security.verificar_senha(senha_nova, atual):
        raise ValueError("A nova senha precisa ser diferente da atual.")

    usuario_repository.atualizar_senha(ator["id"], security.hash_senha(senha_nova), False)
    usuario_repository.apagar_sessoes_do_usuario(ator["id"], manter_hash=security.hash_token(token))


def _criar(perfil, nome, email, ong_id, senha, trocar_senha):
    perfil = validacao.escolha(perfil, "Perfil", PERFIS)
    nome = validacao.nome(nome)
    email = validacao.email(email)

    if perfil == "ong":
        ong_id = validacao.inteiro_id(ong_id, "ONG")

        if not buscar_ong(ong_id):
            raise ValueError("ONG não encontrada.")

        if usuario_repository.contar_ativos("ong", ong_id) >= MAX_CONTAS_ONG:
            raise ValueError(f"Esta ONG já tem {MAX_CONTAS_ONG} contas ativas. Desative uma antes de criar outra.")
    else:
        ong_id = None

    provisoria = None

    if senha is None:
        provisoria = security.senha_provisoria()
        senha = provisoria
    else:
        problema = security.problema_na_senha(senha, email, nome)

        if problema:
            raise ValueError(problema)

    try:
        id_novo = usuario_repository.criar(perfil, ong_id, nome, email, security.hash_senha(senha), trocar_senha)
    except psycopg.errors.UniqueViolation:
        raise ValueError("Já existe uma conta com este e-mail.") from None
    except psycopg.errors.UndefinedTable:
        raise ContasIndisponiveis() from None

    return id_novo, provisoria


def criar_usuario(perfil, nome, email, ong_id=None):
    """O gestor cria a conta e entrega a senha provisoria (que so aparece agora); a pessoa troca no primeiro acesso."""
    id_novo, provisoria = _criar(perfil, nome, email, ong_id, None, True)

    return {"id": id_novo, "senha_provisoria": provisoria}


def criar_conta_ong_pelo_link(ong, nome, email, senha):
    """A pessoa que recebeu o link da ONG escolhe a propria senha; o link e o convite. Ja entra logada."""
    id_novo, _ = _criar("ong", nome, email, ong[0], senha, False)

    return _abrir_sessao(usuario_repository.buscar_para_login(email.strip().lower()))


def listar_usuarios():
    try:
        linhas = usuario_repository.listar()
    except psycopg.errors.UndefinedTable:
        raise ContasIndisponiveis() from None

    return [
        {"id": id_, "perfil": perfil, "ong_id": ong_id, "ong_nome": ong_nome, "nome": nome, "email": email, "ativo": ativo,
         "trocar_senha": trocar, "ultimo_acesso": ultimo, "criado_em": criado}
        for id_, perfil, ong_id, nome, email, ativo, trocar, ong_nome, ultimo, criado in linhas
    ]


def _existente(id_usuario):
    id_usuario = validacao.inteiro_id(id_usuario, "ID da conta")
    linha = usuario_repository.buscar(id_usuario)

    if not linha:
        raise ValueError("Conta não encontrada.")

    return linha


def desativar(id_usuario, ator):
    linha = _existente(id_usuario)

    if ator["tipo"] == "usuario" and ator["id"] == linha[0]:
        raise ValueError("Você não pode desativar a própria conta.")

    if linha[1] == "gestor" and linha[5] and usuario_repository.contar_ativos("gestor") <= 1:
        raise ValueError("Esta é a única conta de gestor ativa. Crie outra antes de desativá-la.")

    usuario_repository.definir_ativo(linha[0], False)


def reativar(id_usuario):
    linha = _existente(id_usuario)

    if linha[1] == "ong" and usuario_repository.contar_ativos("ong", linha[2]) >= MAX_CONTAS_ONG:
        raise ValueError(f"Esta ONG já tem {MAX_CONTAS_ONG} contas ativas.")

    usuario_repository.definir_ativo(linha[0], True)


def redefinir_senha(id_usuario):
    """Nova senha provisoria (aparece uma vez), troca obrigatoria no proximo acesso e sessoes abertas encerradas."""
    linha = _existente(id_usuario)
    provisoria = security.senha_provisoria()
    usuario_repository.atualizar_senha(linha[0], security.hash_senha(provisoria), True)
    usuario_repository.apagar_sessoes_do_usuario(linha[0])

    return {"id": linha[0], "senha_provisoria": provisoria}


def registrar_auditoria(ator, acao, recurso=None, registro_id=None, ip=None):
    """Melhor esforco: um problema na trilha de auditoria nunca derruba a operacao que acabou de dar certo."""
    try:
        usuario_repository.registrar_auditoria(
            ator["tipo"], ator["id"], ator["nome"][:160], acao[:120], recurso, registro_id, ip
        )
    except Exception:  # noqa: BLE001
        logging.warning("Nao foi possivel gravar a auditoria (%s)", acao, exc_info=True)


def auditoria(limite=200):
    try:
        limite = max(1, min(int(limite), 500))
    except (TypeError, ValueError):
        limite = 200

    try:
        linhas = usuario_repository.listar_auditoria(limite)
    except psycopg.errors.UndefinedTable:
        raise ContasIndisponiveis() from None

    return [
        {"id": id_, "quando": quando, "ator_tipo": tipo, "ator_nome": nome, "acao": acao, "recurso": recurso, "registro_id": registro}
        for id_, quando, tipo, nome, acao, recurso, registro in linhas
    ]
