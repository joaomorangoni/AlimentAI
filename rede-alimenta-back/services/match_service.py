from repositories.match_repository import (
    listar_matches,
    buscar_match
)

from repositories import fluxo_repository
from repositories.doacao_repository import buscar_doacao
from repositories.ong_repository import buscar_ong
from services import validacao

PRIORIDADES_VALIDAS = ("baixa", "media", "alta")
STATUS_VALIDOS = ("pendente", "aceito", "recusado", "concluido")
# Fluxo do match: a ONG responde (aceito/recusado) e o gestor conclui a entrega. Recusado e concluido sao finais.
TRANSICOES = {
    "pendente": ("aceito", "recusado"),
    "aceito": ("concluido", "recusado"),
    "recusado": (),
    "concluido": (),
}


def obter_matches():
    return listar_matches()


def obter_match(id_match):
    validacao.inteiro_id(id_match, "ID do match")

    match = buscar_match(id_match)

    if not match:
        raise ValueError("Match não encontrado.")

    return match


def criar_match(
    doacao_id,
    ong_id,
    score_ia,
    prioridade
):
    doacao_id = validacao.inteiro_id(doacao_id, "ID da doação")
    ong_id = validacao.inteiro_id(ong_id, "ID da ONG")
    score_ia = validacao.numero(score_ia, "Score da IA", 0, 1, casas=4)
    prioridade = validacao.escolha(prioridade, "Prioridade", PRIORIDADES_VALIDAS)

    # Verifica se a doação existe
    doacao = buscar_doacao(doacao_id)

    if not doacao:
        raise ValueError("Doação não encontrada.")

    # Verifica se a ONG existe
    ong = buscar_ong(ong_id)

    if not ong:
        raise ValueError("ONG não encontrada.")

    if doacao[6] != "disponivel":
        raise ValueError("Só é possível criar match para uma doação disponível.")

    if validacao.data_iso(str(doacao[5])[:10], "Validade") < validacao.hoje():
        raise ValueError("Esta doação está vencida e não pode receber match.")

    if float(ong[5]) < float(doacao[4]):
        raise ValueError("A ONG não tem capacidade para receber o volume desta doação.")

    for existente in listar_matches():
        if existente[1] == doacao_id and existente[3] == ong_id and existente[7] != "recusado":
            raise ValueError("Já existe um match ativo entre esta doação e esta ONG.")

    # Cria o match e reserva a doacao na mesma transacao.
    return fluxo_repository.criar_match_reservando(
        doacao_id,
        ong_id,
        score_ia,
        prioridade
    )


ORIGENS_CONFIRMACAO = ("gestor", "ong")


def alterar_status_match(id_match, status, origem="gestor"):
    """Aplica uma transicao valida e acerta a doacao junto (recusado libera, concluido encerra).

    `origem` diz quem confirmou a entrega (so conta ao concluir): o gestor pelo painel ou a ONG pelo portal."""
    match = obter_match(id_match)
    status = validacao.escolha(status, "Status do match", STATUS_VALIDOS)

    if status == match[5]:
        return

    if status not in TRANSICOES.get(match[5], ()):
        raise ValueError(f"Não é possível mudar o match de {match[5]} para {status}.")

    fluxo_repository.mudar_status_match(id_match, status, match[5], origem if status == "concluido" else None)


def remover_match(id_match):
    obter_match(id_match)

    # Se o match ainda segurava a doacao, ela volta a ficar disponivel.
    fluxo_repository.excluir_match_liberando(id_match)


if __name__ == "__main__":
    print("MATCHES PELO SERVICE:")
    print("---------------------")

    for match in obter_matches():
        print(match)
