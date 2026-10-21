from repositories.doador_repository import (
    listar_doadores,
    buscar_doador,
    cadastrar_doador,
    atualizar_doador,
    excluir_doador
)

from repositories.doacao_repository import listar_doacoes
from services import validacao


def obter_doadores():
    return listar_doadores()


def obter_doador(id_doador):
    validacao.inteiro_id(id_doador, "ID do doador")

    doador = buscar_doador(id_doador)

    if not doador:
        raise ValueError("Doador não encontrado.")

    return doador


def criar_doador(
    nome,
    email,
    telefone,
    regiao,
    latitude=None,
    longitude=None
):
    nome = validacao.nome(nome)
    email = validacao.email(email)
    telefone = validacao.telefone(telefone)
    regiao = validacao.regiao(regiao)
    latitude, longitude = validacao.coordenadas(latitude, longitude)

    return cadastrar_doador(
        nome,
        email,
        telefone,
        regiao,
        latitude,
        longitude
    )


def editar_doador(
    id_doador,
    nome,
    telefone,
    regiao
):
    obter_doador(id_doador)

    atualizar_doador(
        id_doador,
        validacao.nome(nome),
        validacao.telefone(telefone),
        validacao.regiao(regiao)
    )


def remover_doador(id_doador):
    obter_doador(id_doador)

    # No banco de producao a exclusao seria em cascata e apagaria o historico de doacoes e matches.
    if any(doacao[1] == id_doador for doacao in listar_doacoes()):
        raise ValueError("Não é possível excluir: este doador tem doações cadastradas. Exclua as doações antes.")

    excluir_doador(id_doador)


if __name__ == "__main__":
    print("DOADORES PELO SERVICE:")
    print("----------------------")

    for doador in obter_doadores():
        print(doador)
