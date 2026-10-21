"""Pagina publica de doacao: qualquer pessoa propoe uma oferta; ela fica pendente ate o gestor aprovar ou recusar.

A oferta guarda os dados do doador em ofertas_publicas (nao em doadores): so a aprovacao cria o doador e a doacao.
Quem envia recebe um codigo de acompanhamento (guardado so como hash) para ver em que pe esta a oferta."""
import hashlib
import logging
import re
import secrets

import psycopg

from repositories import fluxo_repository, oferta_repository
from services import doacao_service, validacao

CAMPOS_PERMITIDOS = {
    "nome", "email", "telefone", "regiao", "endereco", "alimento", "categoria", "quantidade_kg", "validade", "aceite", "site",
}
MENSAGEM = "Recebemos sua oferta. Nossa equipe vai analisá-la e entrar em contato."
MAXIMO_PENDENTES_POR_EMAIL = 3
CODIGO = re.compile(r"[A-Za-z0-9_-]{16,64}")


class CodigoInvalido(Exception):
    """Codigo de acompanhamento mal formado ou inexistente (mesma resposta nos dois casos)."""


def hash_codigo(codigo):
    return hashlib.sha256(codigo.encode()).hexdigest()


def criar_oferta(dados):
    """Valida tudo no servidor (a pagina e so conveniencia). Nao devolve ids nem revela se o e-mail ja existe."""
    if not isinstance(dados, dict) or set(dados) - CAMPOS_PERMITIDOS:
        raise ValueError("Dados em formato inválido.")

    # Campo-armadilha: invisivel para pessoas, preenchido por robos. Responde como se tivesse dado certo.
    if dados.get("site"):
        logging.warning("Oferta publica descartada pelo campo-armadilha.")
        return {"mensagem": MENSAGEM, "codigo": secrets.token_urlsafe(16)}

    if dados.get("aceite") is not True:
        raise ValueError("Aceite o aviso de privacidade para enviar a oferta.")

    doador = {
        "nome": validacao.nome(dados.get("nome")),
        "email": validacao.email(dados.get("email")),
        "telefone": validacao.telefone(dados.get("telefone")),
        **validacao.localizacao(dados),
    }
    alimento = doacao_service.validar_alimento(dados.get("alimento"))
    categoria = doacao_service.validar_categoria(dados.get("categoria"))
    quantidade_kg = doacao_service.validar_quantidade(dados.get("quantidade_kg"))
    validade = doacao_service.validar_validade(dados.get("validade"), categoria)

    # A IA e a ultima etapa: so gasta cota com ofertas que passaram em todo o resto.
    doacao_service.validar_com_ia(alimento, categoria)

    doacao = {"alimento": alimento, "categoria": categoria, "quantidade_kg": quantidade_kg, "validade": validade}
    codigo = secrets.token_urlsafe(16)

    try:
        oferta_repository.criar(
            {**doador, **doacao}, hash_codigo(codigo), doacao_service.MAXIMO_PENDENTES, MAXIMO_PENDENTES_POR_EMAIL
        )
    except psycopg.errors.UndefinedTable:
        if "endereco" in doador:
            raise ValueError("Não foi possível salvar o endereço. Tente novamente após a atualização do sistema.") from None
        # Banco ainda sem a migracao 005: segue pelo fluxo antigo (doador e doacao pendente), sem codigo de acompanhamento.
        fluxo_repository.cadastrar_oferta_publica(doador, doacao, doacao_service.MAXIMO_PENDENTES)
        return {"mensagem": MENSAGEM}

    return {"mensagem": MENSAGEM, "codigo": codigo}


def _estado(status_oferta, status_doacao, status_match, nome_ong):
    """(etapa, passo de 1 a 4, titulo, descricao, final) do ponto de vista de quem doou."""
    if status_oferta == "pendente":
        return ("analise", 1, "Estamos analisando a sua oferta",
                "Nossa equipe confere os dados e, se estiver tudo certo, procura uma ONG para receber.", False)
    if status_oferta == "recusada":
        return ("recusada", 1, "Não foi possível aceitar esta oferta",
                "Seus dados pessoais foram apagados do nosso sistema. Você pode enviar uma nova oferta quando quiser.", True)
    if status_doacao == "concluida":
        quem = f"A ONG {nome_ong} confirmou" if nome_ong else "A entrega foi confirmada"
        return ("entregue", 4, "Doação entregue. Obrigado!", f"{quem}. O seu alimento chegou a quem precisa.", True)
    if status_doacao == "cancelada" or status_doacao is None:
        return ("encerrada", 2, "Esta oferta foi encerrada",
                "A doação foi cancelada pela nossa equipe. Se tiver dúvidas, fale com a gente.", True)
    if status_doacao == "reservada" and status_match == "aceito":
        return ("ong_aceitou", 3, "Uma ONG aceitou a sua doação",
                f"A ONG {nome_ong} vai entrar em contato com você para combinar a retirada." if nome_ong
                else "A ONG vai entrar em contato com você para combinar a retirada.", False)
    if status_doacao == "reservada":
        return ("ong_indicada", 3, "Uma ONG foi indicada",
                "A organização escolhida vai responder em breve. Assim que aceitar, ela entra em contato.", False)
    return ("procurando_ong", 2, "Oferta aprovada!",
            "Estamos procurando a ONG mais indicada para receber o seu alimento.", False)


def acompanhar(codigo):
    """Em que pe esta uma oferta, a partir do codigo que o doador recebeu. Nao revela dados pessoais de ninguem."""
    if not isinstance(codigo, str) or not CODIGO.fullmatch(codigo):
        raise CodigoInvalido()

    try:
        linha = oferta_repository.acompanhar(hash_codigo(codigo))
    except psycopg.errors.UndefinedTable:
        linha = None

    if not linha:
        raise CodigoInvalido()

    status_oferta, alimento, quantidade, enviada_em, status_doacao, status_match, nome_ong = linha
    etapa, passo, titulo, descricao, final = _estado(status_oferta, status_doacao, status_match, nome_ong)

    return {
        "etapa": etapa, "passo": passo, "titulo": titulo, "descricao": descricao, "final": final,
        "alimento": alimento, "quantidade_kg": float(quantidade), "enviada_em": enviada_em,
    }
