"""Ofertas da pagina publica: ficam em ofertas_publicas ate o gestor aprovar (cria doador e doacao) ou recusar."""
import psycopg

from psycopg.types.json import Jsonb

from database.connection import conectar
from repositories.fluxo_repository import _transacao

# Estado da oferta visto pelo doador, a partir da oferta, da doacao e do match mais recente que ainda vale.
_ACOMPANHAMENTO = """
    SELECT o.status, o.alimento, o.quantidade_kg, o.criado_em, d.status,
           (SELECT m.status FROM matches m
             WHERE m.doacao_id = d.id AND m.status IN ('pendente', 'aceito', 'concluido')
             ORDER BY m.id DESC LIMIT 1),
           (SELECT og.nome FROM matches m JOIN ongs og ON og.id = m.ong_id
             WHERE m.doacao_id = d.id AND m.status IN ('aceito', 'concluido')
             ORDER BY m.id DESC LIMIT 1)
    FROM ofertas_publicas o
    LEFT JOIN doacoes d ON d.id = o.doacao_id
    WHERE o.codigo_hash = %s;
"""


def criar(oferta, codigo_hash, limite_pendentes, limite_por_email):
    """Grava a oferta como pendente. Recusa excesso de pendentes (total e por e-mail) e oferta repetida."""
    def operacao(cursor):
        cursor.execute("SELECT count(*) FROM ofertas_publicas WHERE status = 'pendente';")

        if cursor.fetchone()[0] >= limite_pendentes:
            raise ValueError("Há muitas ofertas aguardando análise. Tente novamente mais tarde.")

        cursor.execute(
            "SELECT count(*) FROM ofertas_publicas WHERE status = 'pendente' AND email = %s;", (oferta["email"],)
        )

        if cursor.fetchone()[0] >= limite_por_email:
            raise ValueError("Você já tem ofertas aguardando análise. Aguarde a resposta da nossa equipe.")

        cursor.execute(
            """
            SELECT 1 FROM ofertas_publicas o LEFT JOIN doacoes d ON d.id = o.doacao_id
            WHERE o.email = %s AND lower(o.alimento) = lower(%s) AND o.validade = %s AND o.quantidade_kg = %s
              AND (o.status = 'pendente' OR (o.status = 'aprovada' AND d.status IN ('disponivel', 'reservada')));
            """,
            (oferta["email"], oferta["alimento"], oferta["validade"], oferta["quantidade_kg"])
        )

        if cursor.fetchone():
            raise ValueError("Esta oferta já foi enviada.")

        cursor.execute(
            """
            INSERT INTO ofertas_publicas
                (codigo_hash, nome, email, telefone, regiao, alimento, categoria, quantidade_kg, validade, endereco)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
            """,
            (codigo_hash, oferta["nome"], oferta["email"], oferta["telefone"], oferta["regiao"], oferta["alimento"],
             oferta["categoria"], oferta["quantidade_kg"], oferta["validade"], Jsonb(oferta.get("endereco")))
        )
        return cursor.fetchone()[0]

    return _transacao(operacao)


def listar_pendentes():
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT id, nome, email, telefone, regiao, alimento, categoria, quantidade_kg, validade, criado_em, endereco
                FROM ofertas_publicas
                WHERE status = 'pendente'
                ORDER BY id DESC;
            """)
            return cursor.fetchall()

    finally:
        conexao.close()


def aprovar(id_oferta, hoje):
    """Cria (ou reaproveita, pelo e-mail) o doador e a doacao DISPONIVEL e marca a oferta como aprovada, em uma transacao."""
    def operacao(cursor):
        cursor.execute(
            """
            SELECT nome, email, telefone, regiao, alimento, categoria, quantidade_kg, validade, status
            FROM ofertas_publicas WHERE id = %s FOR UPDATE;
            """,
            (id_oferta,)
        )
        linha = cursor.fetchone()

        if not linha or linha[8] != "pendente":
            raise ValueError("Só é possível aprovar uma oferta pendente. Atualize a página.")

        nome, email, telefone, regiao, alimento, categoria, quantidade, validade, _ = linha

        if validade < hoje:
            raise ValueError("A validade desta oferta já passou. Recuse a oferta.")

        cursor.execute("SELECT id FROM doadores WHERE email = %s;", (email,))
        existente = cursor.fetchone()

        if existente:
            doador_id = existente[0]
        else:
            cursor.execute(
                "INSERT INTO doadores (nome, email, telefone, regiao) VALUES (%s, %s, %s, %s) RETURNING id;",
                (nome, email, telefone, regiao)
            )
            doador_id = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT 1 FROM doacoes
            WHERE doador_id = %s AND lower(alimento) = lower(%s) AND validade = %s AND quantidade_kg = %s
              AND status IN ('pendente', 'disponivel');
            """,
            (doador_id, alimento, validade, quantidade)
        )

        if cursor.fetchone():
            raise ValueError("Já existe uma doação disponível idêntica deste doador. Recuse a oferta.")

        cursor.execute(
            """
            INSERT INTO doacoes (doador_id, alimento, categoria, quantidade_kg, validade, status)
            VALUES (%s, %s, %s, %s, %s, 'disponivel') RETURNING id;
            """,
            (doador_id, alimento, categoria, quantidade, validade)
        )
        doacao_id = cursor.fetchone()[0]
        cursor.execute(
            "UPDATE ofertas_publicas SET status = 'aprovada', doacao_id = %s, decidido_em = CURRENT_TIMESTAMP WHERE id = %s;",
            (doacao_id, id_oferta)
        )
        return doacao_id

    return _transacao(operacao)


def recusar(id_oferta):
    """Recusa a oferta pendente e apaga os dados pessoais dela (sobra so o que e do alimento, para auditoria)."""
    def operacao(cursor):
        cursor.execute(
            """
            UPDATE ofertas_publicas
            SET status = 'recusada', decidido_em = CURRENT_TIMESTAMP,
                nome = '(removido)', email = 'removido-' || id || '@invalido', telefone = NULL, regiao = NULL, endereco = NULL
            WHERE id = %s AND status = 'pendente';
            """,
            (id_oferta,)
        )
        return cursor.rowcount == 1

    return _transacao(operacao)


def acompanhar(codigo_hash):
    """(status_da_oferta, alimento, kg, enviada_em, status_da_doacao, status_do_match, nome_da_ong) ou None."""
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute(_ACOMPANHAMENTO, (codigo_hash,))
            return cursor.fetchone()

    finally:
        conexao.close()


def inicio_por_doacao():
    """{id_da_doacao: momento em que o doador enviou a oferta}, para medir o tempo ate o match. {} sem a migracao."""
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            try:
                cursor.execute("SELECT doacao_id, criado_em FROM ofertas_publicas WHERE doacao_id IS NOT NULL;")
            except psycopg.errors.UndefinedTable:
                return {}

            return dict(cursor.fetchall())

    finally:
        conexao.close()
