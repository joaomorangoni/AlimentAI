"""Portal da ONG (acesso por link com codigo): a ONG ve so os matches dela e aceita ou recusa."""
import psycopg

import security
from repositories import fluxo_repository
from repositories.doacao_repository import buscar_doacao
from repositories.match_repository import buscar_match
from repositories.ong_repository import buscar_ong
from services import match_service, validacao

STATUS_COM_CONTATO = ("aceito", "concluido")


class AcessoNegado(Exception):
    """Link invalido, expirado ou de outra ONG."""


def _info(ong_id):
    """(versao, gerado_em, ativo) do link. Sem a tabela dos links (migracao 001), vale o link original e ativo."""
    try:
        return fluxo_repository.obter_info_link(ong_id)
    except psycopg.errors.UndefinedTable:
        return 1, None, True


def _resposta_link(ong_id, versao, gerado_em, ativo=True):
    """O gerado_em e None para o link original (nunca renovado): vale desde o cadastro da ONG."""
    return {"caminho": f"/ong#{ong_id}.{security.codigo_link_ong(ong_id, versao)}", "versao": versao,
            "gerado_em": gerado_em, "ativo": ativo}


def link_da_ong(ong_id):
    """Caminho do link de acesso da ONG (o codigo fica no fragmento #, que nao vai para logs nem Referer), de quando e e se esta ativo."""
    validacao.inteiro_id(ong_id, "ID da ONG")

    if not buscar_ong(ong_id):
        raise ValueError("ONG não encontrada.")

    versao, gerado_em, ativo = _info(ong_id)

    return _resposta_link(ong_id, versao, gerado_em, ativo)


def renovar_link(ong_id):
    """Gera um link novo (o anterior deixa de funcionar) e reativa o acesso por link se estava desativado."""
    validacao.inteiro_id(ong_id, "ID da ONG")

    if not buscar_ong(ong_id):
        raise ValueError("ONG não encontrada.")

    try:
        versao, gerado_em = fluxo_repository.renovar_link(ong_id)
    except psycopg.errors.UndefinedTable:
        raise ValueError("Renovação indisponível: aplique a migração do banco (python migrar.py).") from None

    return _resposta_link(ong_id, versao, gerado_em, True)


def desativar_link(ong_id):
    """Ninguem mais entra por link nessa ONG; so por e-mail e senha. Gerar um link novo reativa."""
    validacao.inteiro_id(ong_id, "ID da ONG")

    if not buscar_ong(ong_id):
        raise ValueError("ONG não encontrada.")

    try:
        fluxo_repository.definir_link_ativo(ong_id, False)
    except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn):
        raise ValueError("Desativar o link exige a migração 007 do banco (reinicie o servidor ou rode python migrar.py).") from None

    return link_da_ong(ong_id)


def autenticar(ong_id, codigo):
    """Devolve a ONG se o codigo confere com a versao vigente e o link esta ativo; senao AcessoNegado (mensagem unica)."""
    if isinstance(ong_id, bool) or not isinstance(ong_id, int) or not 1 <= ong_id <= validacao.ID_MAXIMO:
        raise AcessoNegado()

    ong = buscar_ong(ong_id)

    if not ong:
        raise AcessoNegado()

    versao, _, ativo = _info(ong_id)

    if not ativo or not security.codigo_link_valido(codigo, ong_id, versao):
        raise AcessoNegado()

    return ong


def ong_da_conta(ator):
    """A ONG de uma conta de usuario (perfil ong); AcessoNegado se ela deixou de existir."""
    ong = buscar_ong(ator["ong_id"]) if ator.get("ong_id") else None

    if not ong:
        raise AcessoNegado()

    return ong


def painel(ong):
    """Matches da ONG. O contato do doador so aparece depois que a ONG aceita."""
    itens = []

    for id_, status, prioridade, alimento, categoria, quantidade, validade, regiao, nome, email, telefone in \
            fluxo_repository.matches_da_ong(ong[0]):
        item = {
            "id": id_, "status": status, "prioridade": prioridade, "alimento": alimento, "categoria": categoria,
            "quantidade_kg": float(quantidade), "validade": validade, "regiao_doador": regiao,
        }

        if status in STATUS_COM_CONTATO:
            item["doador"] = {"nome": nome, "email": email, "telefone": telefone}

        itens.append(item)

    return {"ong": {"nome": ong[1], "regiao": ong[4]}, "matches": itens}


def responder(ong, id_match, aceitar):
    """A ONG aceita ou recusa um match pendente que seja dela (outro match responde como inexistente)."""
    id_match = validacao.inteiro_id(id_match, "ID do match")
    match = buscar_match(id_match)

    if not match or match[2] != ong[0]:
        raise ValueError("Match não encontrado.")

    if match[5] != "pendente":
        raise ValueError("Este match já foi respondido.")

    if aceitar:
        doacao = buscar_doacao(match[1])

        if not doacao or validacao.data_iso(str(doacao[5])[:10], "Validade") < validacao.hoje():
            raise ValueError("Esta doação já passou da validade e não pode ser aceita.")

    match_service.alterar_status_match(id_match, "aceito" if aceitar else "recusado")


def confirmar_recebimento(ong, id_match):
    """A ONG confirma que recebeu o alimento de um match que ela aceitou: a entrega passa a contar como concluida."""
    id_match = validacao.inteiro_id(id_match, "ID do match")
    match = buscar_match(id_match)

    if not match or match[2] != ong[0]:
        raise ValueError("Match não encontrado.")

    if match[5] != "aceito":
        raise ValueError("Só é possível confirmar o recebimento de uma doação que você aceitou e ainda não foi concluída.")

    match_service.alterar_status_match(id_match, "concluido", origem="ong")
