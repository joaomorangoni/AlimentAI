import psycopg

from repositories.ong_repository import (
    listar_ongs,
    listar_ongs_com_cnpj,
    buscar_ong,
    cadastrar_ong,
    atualizar_ong,
    excluir_ong
)

from repositories.match_repository import listar_matches
from services import validacao

CAPACIDADE_MAXIMA_KG = 1000000


def obter_ongs():
    try:
        return listar_ongs_com_cnpj()
    except psycopg.errors.UndefinedColumn:
        return [(*ong, None) for ong in listar_ongs()]  # migracao 004 ainda nao aplicada


def obter_ong(id_ong):
    validacao.inteiro_id(id_ong, "ID da ONG")

    ong = buscar_ong(id_ong)

    if not ong:
        raise ValueError("ONG não encontrada.")

    return ong


def validar_capacidade(capacidade_kg):
    return validacao.numero(
        capacidade_kg, "Capacidade", 0, CAPACIDADE_MAXIMA_KG, casas=2, minimo_exclusivo=True
    )


def criar_ong(
    nome,
    email,
    telefone,
    regiao,
    capacidade_kg,
    latitude=None,
    longitude=None,
    cnpj=None
):
    nome = validacao.nome(nome)
    email = validacao.email(email)
    telefone = validacao.telefone(telefone)
    regiao = validacao.regiao(regiao)
    capacidade_kg = validar_capacidade(capacidade_kg)
    latitude, longitude = validacao.coordenadas(latitude, longitude)
    cnpj = validacao.cnpj(cnpj)

    return cadastrar_ong(
        nome,
        email,
        telefone,
        regiao,
        capacidade_kg,
        latitude,
        longitude,
        cnpj
    )


_MANTER = object()


def editar_ong(
    id_ong,
    nome,
    telefone,
    regiao,
    capacidade_kg,
    cnpj=_MANTER
):
    obter_ong(id_ong)

    atualizar_ong(
        id_ong,
        validacao.nome(nome),
        validacao.telefone(telefone),
        validacao.regiao(regiao),
        validar_capacidade(capacidade_kg),
        cnpj is not _MANTER,
        None if cnpj is _MANTER else validacao.cnpj(cnpj)
    )


def remover_ong(id_ong):
    obter_ong(id_ong)

    # No banco de producao a exclusao seria em cascata e apagaria o historico de matches.
    if any(match[3] == id_ong for match in listar_matches()):
        raise ValueError("Não é possível excluir: esta ONG tem matches registrados. Exclua os matches antes.")

    excluir_ong(id_ong)


if __name__ == "__main__":
    print("ONGS PELO SERVICE:")
    print("------------------")

    for ong in obter_ongs():
        print(ong)
