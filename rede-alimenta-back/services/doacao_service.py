import re
from datetime import timedelta

from ia import validador_alimento
from services import validacao

from repositories.doacao_repository import (
    listar_doacoes,
    buscar_doacao,
    cadastrar_doacao,
    atualizar_doacao,
    excluir_doacao
)

from repositories import fluxo_repository
from repositories.doador_repository import buscar_doador
from repositories.match_repository import listar_matches

QUANTIDADE_MAXIMA_KG = 10000
CATEGORIAS_VALIDAS = validador_alimento.CATEGORIAS
STATUS_VALIDOS = ("pendente", "disponivel", "reservada", "concluida", "cancelada")
MAXIMO_PENDENTES = 100
ROTULOS_CATEGORIA = {
    "hortifruti": "Hortifrúti",
    "padaria": "Padaria",
    "laticinios": "Laticínios",
    "carnes": "Carnes",
    "prontos": "Pratos prontos",
    "nao_perecivel": "Não perecível",
}
# Prazo maximo de validade por categoria, a partir de hoje: validade fora disso nao faz sentido para o tipo de alimento.
VALIDADE_MAXIMA_DIAS = {
    "hortifruti": 60,
    "padaria": 90,
    "laticinios": 365,
    "carnes": 365,
    "prontos": 180,
    "nao_perecivel": 1095,
}
ALIMENTO_REGEX = re.compile(r"^[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 .,'/()%-]{1,59}$")


class ValidacaoIndisponivel(Exception):
    """Nenhuma validacao (lista local ou IA) conseguiu confirmar que o item e um alimento."""


def validar_alimento(alimento):
    limpo = validacao.texto(alimento, "Alimento", 2, 60)
    if not ALIMENTO_REGEX.match(limpo):
        raise ValueError("Alimento deve ter de 2 a 60 caracteres, começando por letra.")
    return limpo


def validar_categoria(categoria):
    if categoria not in CATEGORIAS_VALIDAS:
        raise ValueError("Categoria inválida. Escolha uma das opções da lista.")
    return categoria


def validar_quantidade(quantidade_kg):
    return validacao.numero(
        quantidade_kg, "Quantidade", 0, QUANTIDADE_MAXIMA_KG, casas=2, minimo_exclusivo=True
    )


def validar_validade(validade, categoria, checar_passado=True):
    """Validade existente no calendario, nao vencida e coerente com o tipo de alimento."""
    validar_categoria(categoria)
    data = validacao.data_iso(validade, "Validade")
    hoje = validacao.hoje()

    if checar_passado and data < hoje:
        raise ValueError("A validade do alimento não pode estar vencida.")

    limite = VALIDADE_MAXIMA_DIAS[categoria]

    if data > hoje + timedelta(days=limite):
        raise ValueError(
            f"Validade muito distante para {ROTULOS_CATEGORIA[categoria]} (máximo de {limite} dias). "
            "Confira a data e a categoria."
        )

    return data


def validar_com_ia(alimento, categoria):
    """Bloqueio local, lista conhecida e IA, nessa ordem. Nega por padrao: sem confirmacao, nao cadastra.

    Item que nao e alimento ou que esta na categoria errada e sempre recusado."""
    validar_categoria(categoria)
    veredito = validador_alimento.avaliar(alimento)

    if veredito is None:
        if validador_alimento.falha_aberta():
            return

        raise ValidacaoIndisponivel(
            "Não foi possível confirmar agora que este item é um alimento. Tente novamente em instantes."
        )

    if not veredito["alimento"]:
        raise ValueError(f"\"{alimento}\" não parece ser um alimento. Revise o nome e tente novamente.")

    if categoria not in veredito["aceitas"]:
        raise ValueError(
            f"\"{alimento}\" pertence à categoria {ROTULOS_CATEGORIA[veredito['categoria']]}, "
            f"não {ROTULOS_CATEGORIA[categoria]}. Corrija a categoria."
        )


def obter_doacoes():
    return listar_doacoes()


def obter_doacao(id_doacao):
    validacao.inteiro_id(id_doacao, "ID da doação")

    doacao = buscar_doacao(id_doacao)

    if not doacao:
        raise ValueError("Doação não encontrada.")

    return doacao


def criar_doacao(
    doador_id,
    alimento,
    categoria,
    quantidade_kg,
    validade
):
    doador_id = validacao.inteiro_id(doador_id, "Doador")
    alimento = validar_alimento(alimento)
    categoria = validar_categoria(categoria)
    quantidade_kg = validar_quantidade(quantidade_kg)
    validade = validar_validade(validade, categoria)

    # Verifica se o doador existe
    if not buscar_doador(doador_id):
        raise ValueError("Doador não encontrado.")

    for existente in listar_doacoes():
        if (
            existente[1] == doador_id
            and str(existente[3]).strip().lower() == alimento.lower()
            and existente[7] == "disponivel"
            and str(existente[6])[:10] == validade.isoformat()
            and float(existente[5]) == quantidade_kg
        ):
            raise ValueError("Já existe uma doação disponível idêntica deste doador.")

    # A consulta a IA e a ultima etapa: so gasta cota com cadastros que passaram em todo o resto.
    validar_com_ia(alimento, categoria)

    return cadastrar_doacao(
        doador_id,
        alimento,
        categoria,
        quantidade_kg,
        validade
    )


def editar_doacao(
    id_doacao,
    alimento,
    categoria,
    quantidade_kg,
    validade,
    status
):
    atual = obter_doacao(id_doacao)

    alimento = validar_alimento(alimento)
    categoria = validar_categoria(categoria)
    quantidade_kg = validar_quantidade(quantidade_kg)
    nova_validade = validacao.data_iso(validade, "Validade")
    validade_mudou = str(atual[5])[:10] != nova_validade.isoformat()
    validade = validar_validade(nova_validade, categoria, checar_passado=validade_mudou)
    status = validacao.escolha(status, "Status da doação", STATUS_VALIDOS)

    if status == "pendente" and atual[6] != "pendente":
        raise ValueError("Uma doação não pode voltar a ficar pendente.")

    # Alimento e categoria ja aprovados no cadastro so voltam para a IA se forem alterados.
    if alimento != atual[2] or categoria != atual[3]:
        validar_com_ia(alimento, categoria)

    atualizar_doacao(
        id_doacao,
        alimento,
        categoria,
        quantidade_kg,
        validade,
        status
    )


def aprovar_doacao(id_doacao):
    """O gestor aprova uma oferta pendente (vinda da pagina publica): ela passa a ficar disponivel."""
    doacao = obter_doacao(id_doacao)

    if doacao[6] != "pendente":
        raise ValueError("Só é possível aprovar uma oferta pendente.")

    if validacao.data_iso(str(doacao[5])[:10], "Validade") < validacao.hoje():
        raise ValueError("A validade desta oferta já passou. Recuse a oferta.")

    if not fluxo_repository.atualizar_status_doacao(id_doacao, "disponivel", "pendente"):
        raise ValueError("A oferta mudou de status. Atualize a página.")


def recusar_doacao(id_doacao):
    """O gestor recusa uma oferta pendente: o registro fica como cancelado, para auditoria."""
    doacao = obter_doacao(id_doacao)

    if doacao[6] != "pendente":
        raise ValueError("Só é possível recusar uma oferta pendente.")

    if not fluxo_repository.atualizar_status_doacao(id_doacao, "cancelada", "pendente"):
        raise ValueError("A oferta mudou de status. Atualize a página.")


def remover_doacao(id_doacao):
    obter_doacao(id_doacao)

    # No banco de producao a exclusao seria em cascata e apagaria o historico de matches.
    if any(match[1] == id_doacao for match in listar_matches()):
        raise ValueError("Não é possível excluir: esta doação tem matches registrados. Exclua os matches antes.")

    excluir_doacao(id_doacao)


if __name__ == "__main__":
    print("DOAÇÕES PELO SERVICE:")
    print("---------------------")

    for doacao in obter_doacoes():
        print(doacao)
