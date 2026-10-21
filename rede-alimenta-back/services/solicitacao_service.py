"""Pedido de acesso ao portal: a ONG pede pela pagina publica e o administrador decide e envia o link."""
import logging

import psycopg

from repositories import solicitacao_repository
from services import ong_service, validacao

CAMPOS_PERMITIDOS = {"nome", "email", "telefone", "regiao", "endereco", "mensagem", "cnpj", "capacidade_kg", "aceite", "site"}
MAXIMO_PENDENTES = 200
MENSAGEM = "Recebemos seu pedido. O administrador vai analisá-lo e, se aprovado, enviará o link de acesso."


def _mensagem(valor):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None

    return validacao.texto(valor, "Mensagem", 2, 500)


def _capacidade(valor):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None

    return ong_service.validar_capacidade(valor)


def criar_pedido(dados):
    """Valida tudo no servidor. A resposta e sempre a mesma: nao revela se o e-mail ja e de uma ONG nem se ja havia pedido."""
    if not isinstance(dados, dict) or set(dados) - CAMPOS_PERMITIDOS:
        raise ValueError("Dados em formato inválido.")

    if dados.get("site"):
        logging.warning("Pedido de acesso descartado pelo campo-armadilha.")
        return {"mensagem": MENSAGEM}

    if dados.get("aceite") is not True:
        raise ValueError("Aceite o aviso de privacidade para enviar o pedido.")

    pedido = {
        "nome": validacao.nome(dados.get("nome"), "Nome da organização"),
        "email": validacao.email(dados.get("email")),
        "telefone": validacao.telefone(dados.get("telefone")),
        **validacao.localizacao(dados),
        "mensagem": _mensagem(dados.get("mensagem")),
        "cnpj": validacao.cnpj(dados.get("cnpj")),
        "capacidade_kg": _capacidade(dados.get("capacidade_kg")),
    }

    try:
        solicitacao_repository.criar_pendente(pedido, MAXIMO_PENDENTES)
    except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
        raise ValueError("Pedidos de acesso indisponíveis no momento. Fale diretamente com o administrador.") from None

    return {"mensagem": MENSAGEM}


def listar():
    try:
        linhas = solicitacao_repository.listar_pendentes()
    except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
        return []

    return [
        {"id": id_, "nome": nome, "email": email, "telefone": telefone, "regiao": regiao, "endereco": endereco[0] if endereco else None, "mensagem": mensagem,
         "criado_em": criado_em, "ong_id": ong_id, "cnpj": cnpj,
         "capacidade_kg": float(capacidade) if capacidade is not None else None}
        for id_, nome, email, telefone, regiao, mensagem, criado_em, ong_id, cnpj, capacidade, *endereco in linhas
    ]


def encerrar(id_solicitacao, atendida):
    id_solicitacao = validacao.inteiro_id(id_solicitacao, "ID do pedido")

    if not solicitacao_repository.encerrar(id_solicitacao, "atendida" if atendida else "descartada"):
        raise ValueError("Pedido não encontrado ou já encerrado.")
