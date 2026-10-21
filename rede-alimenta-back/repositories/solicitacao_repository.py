"""Pedidos de acesso ao portal feitos por ONGs."""
from psycopg.types.json import Jsonb

from database.connection import conectar
from repositories.fluxo_repository import _transacao


def criar_pendente(solicitacao, limite_pendentes):
    """Grava o pedido. Um e-mail so tem um pedido pendente por vez; o excedente e ignorado em silencio."""
    def operacao(cursor):
        cursor.execute("SELECT count(*) FROM ong_solicitacoes_acesso WHERE status = 'pendente';")

        if cursor.fetchone()[0] >= limite_pendentes:
            raise ValueError("Há muitos pedidos aguardando análise. Tente novamente mais tarde.")

        cursor.execute(
            "SELECT 1 FROM ong_solicitacoes_acesso WHERE status = 'pendente' AND email = %s;", (solicitacao["email"],)
        )

        if cursor.fetchone():
            return False

        cursor.execute(
            """
            INSERT INTO ong_solicitacoes_acesso (nome, email, telefone, regiao, mensagem, cnpj, capacidade_kg, endereco)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """,
            (solicitacao["nome"], solicitacao["email"], solicitacao["telefone"], solicitacao["regiao"], solicitacao["mensagem"],
             solicitacao["cnpj"], solicitacao["capacidade_kg"], Jsonb(solicitacao.get("endereco")))
        )
        return True

    return _transacao(operacao)


def listar_pendentes():
    """Pedidos pendentes, com o id da ONG cadastrada que tem o mesmo e-mail (ou None)."""
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT s.id, s.nome, s.email, s.telefone, s.regiao, s.mensagem, s.criado_em, o.id, s.cnpj, s.capacidade_kg, s.endereco
                FROM ong_solicitacoes_acesso s
                LEFT JOIN ongs o ON lower(o.email) = s.email
                WHERE s.status = 'pendente'
                ORDER BY s.id DESC;
            """)
            return cursor.fetchall()

    finally:
        conexao.close()


def encerrar(id_solicitacao, novo_status):
    """Marca um pedido pendente como atendido ou descartado. Retorna True se mudou.

    Descartar apaga os dados pessoais do pedido (nome, e-mail, telefone, mensagem, CNPJ); sobra so o registro da decisao."""
    def operacao(cursor):
        if novo_status == "descartada":
            cursor.execute(
                """
                UPDATE ong_solicitacoes_acesso
                SET status = 'descartada', nome = '(removido)', email = 'removido-' || id || '@invalido',
                    telefone = NULL, regiao = '(removido)', endereco = NULL, mensagem = NULL, cnpj = NULL, capacidade_kg = NULL
                WHERE id = %s AND status = 'pendente';
                """,
                (id_solicitacao,)
            )
        else:
            cursor.execute(
                "UPDATE ong_solicitacoes_acesso SET status = %s WHERE id = %s AND status = 'pendente';",
                (novo_status, id_solicitacao)
            )

        return cursor.rowcount == 1

    return _transacao(operacao)
