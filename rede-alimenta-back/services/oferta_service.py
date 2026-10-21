"""Ofertas da pagina publica vistas pelo gestor: listar as pendentes, aprovar (cria doador e doacao) ou recusar."""
import psycopg

from repositories import oferta_repository
from services import validacao


def listar():
    try:
        linhas = oferta_repository.listar_pendentes()
    except psycopg.errors.UndefinedTable:
        return []  # banco sem a migracao 005: ainda nao existe fila de ofertas

    return [
        {"id": id_, "nome": nome, "email": email, "telefone": telefone, "regiao": regiao, "endereco": endereco[0] if endereco else None, "alimento": alimento,
         "categoria": categoria, "quantidade_kg": float(quantidade), "validade": validade, "criado_em": criado_em}
        for id_, nome, email, telefone, regiao, alimento, categoria, quantidade, validade, criado_em, *endereco in linhas
    ]


def aprovar(id_oferta):
    """Cria o doador (ou reaproveita o do mesmo e-mail) e a doacao disponivel. Devolve o id da doacao."""
    id_oferta = validacao.inteiro_id(id_oferta, "ID da oferta")

    return oferta_repository.aprovar(id_oferta, validacao.hoje())


def recusar(id_oferta):
    id_oferta = validacao.inteiro_id(id_oferta, "ID da oferta")

    if not oferta_repository.recusar(id_oferta):
        raise ValueError("Só é possível recusar uma oferta pendente. Atualize a página.")
