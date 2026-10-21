"""Operacoes que alteram mais de uma tabela de uma vez (transacao unica), usadas pelo fluxo doacao -> match -> entrega."""
import psycopg

from database.connection import conectar


def _transacao(funcao):
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            resultado = funcao(cursor)

        conexao.commit()
        return resultado

    except Exception:
        conexao.rollback()
        raise

    finally:
        conexao.close()


def atualizar_status_doacao(id_doacao, novo_status, status_atual):
    """Muda o status so se a doacao ainda estiver no status esperado. Retorna True se mudou."""
    def operacao(cursor):
        cursor.execute(
            "UPDATE doacoes SET status = %s WHERE id = %s AND status = %s;",
            (novo_status, id_doacao, status_atual)
        )
        return cursor.rowcount == 1

    return _transacao(operacao)


def cadastrar_oferta_publica(doador, doacao, limite_pendentes):
    """Reaproveita o doador pelo e-mail (sem alterar os dados dele) e cria a doacao como pendente."""
    def operacao(cursor):
        cursor.execute("SELECT count(*) FROM doacoes WHERE status = 'pendente';")

        if cursor.fetchone()[0] >= limite_pendentes:
            raise ValueError("Há muitas ofertas aguardando análise. Tente novamente mais tarde.")

        cursor.execute("SELECT id FROM doadores WHERE email = %s;", (doador["email"],))
        existente = cursor.fetchone()

        if existente:
            doador_id = existente[0]
        else:
            cursor.execute(
                "INSERT INTO doadores (nome, email, telefone, regiao) VALUES (%s, %s, %s, %s) RETURNING id;",
                (doador["nome"], doador["email"], doador["telefone"], doador["regiao"])
            )
            doador_id = cursor.fetchone()[0]

        cursor.execute("SELECT count(*) FROM doacoes WHERE doador_id = %s AND status = 'pendente';", (doador_id,))

        if cursor.fetchone()[0] >= 3:
            raise ValueError("Você já tem ofertas aguardando análise. Aguarde a resposta da nossa equipe.")

        cursor.execute(
            """
            SELECT 1 FROM doacoes
            WHERE doador_id = %s AND lower(alimento) = lower(%s) AND validade = %s
              AND quantidade_kg = %s AND status IN ('pendente', 'disponivel');
            """,
            (doador_id, doacao["alimento"], doacao["validade"], doacao["quantidade_kg"])
        )

        if cursor.fetchone():
            raise ValueError("Esta oferta já foi enviada.")

        cursor.execute(
            """
            INSERT INTO doacoes (doador_id, alimento, categoria, quantidade_kg, validade, status)
            VALUES (%s, %s, %s, %s, %s, 'pendente') RETURNING id;
            """,
            (doador_id, doacao["alimento"], doacao["categoria"], doacao["quantidade_kg"], doacao["validade"])
        )
        return cursor.fetchone()[0]

    return _transacao(operacao)


def criar_match_reservando(doacao_id, ong_id, score_ia, prioridade):
    """Cria o match e reserva a doacao de forma atomica: duas pessoas nao reservam a mesma doacao."""
    def operacao(cursor):
        cursor.execute(
            "UPDATE doacoes SET status = 'reservada' WHERE id = %s AND status = 'disponivel';",
            (doacao_id,)
        )

        if cursor.rowcount != 1:
            raise ValueError("Esta doação não está mais disponível.")

        cursor.execute(
            """
            INSERT INTO matches (doacao_id, ong_id, score_ia, prioridade, status)
            VALUES (%s, %s, %s, %s, 'pendente') RETURNING id;
            """,
            (doacao_id, ong_id, score_ia, prioridade)
        )
        return cursor.fetchone()[0]

    return _transacao(operacao)


def mudar_status_match(id_match, novo_status, status_esperado, origem=None):
    """Muda o status do match e acerta a doacao: recusado libera, concluido encerra (e registra quem confirmou)."""
    def operacao(cursor):
        cursor.execute(
            "SELECT doacao_id FROM matches WHERE id = %s AND status = %s FOR UPDATE;",
            (id_match, status_esperado)
        )
        linha = cursor.fetchone()

        if not linha:
            raise ValueError("O status deste match mudou. Atualize a página.")

        cursor.execute("UPDATE matches SET status = %s WHERE id = %s;", (novo_status, id_match))

        if novo_status == "recusado":
            cursor.execute(
                "UPDATE doacoes SET status = 'disponivel' WHERE id = %s AND status = 'reservada';",
                (linha[0],)
            )
        elif novo_status == "concluido":
            cursor.execute(
                "UPDATE doacoes SET status = 'concluida' WHERE id = %s AND status IN ('reservada', 'disponivel');",
                (linha[0],)
            )

            if origem:
                _registrar_confirmacao(cursor, id_match, origem)

    return _transacao(operacao)


def _registrar_confirmacao(cursor, id_match, origem):
    """Guarda quem confirmou a entrega. Sem a migracao 006 a tabela nao existe: o savepoint evita derrubar a conclusao."""
    cursor.execute("SAVEPOINT confirmacao;")

    try:
        cursor.execute(
            "INSERT INTO match_confirmacoes (match_id, origem) VALUES (%s, %s) ON CONFLICT (match_id) DO NOTHING;",
            (id_match, origem)
        )
    except psycopg.errors.UndefinedTable:
        cursor.execute("ROLLBACK TO SAVEPOINT confirmacao;")


def excluir_match_liberando(id_match):
    """Exclui o match; se ele ainda segurava a doacao, ela volta a ficar disponivel."""
    def operacao(cursor):
        cursor.execute("SELECT doacao_id, status FROM matches WHERE id = %s FOR UPDATE;", (id_match,))
        linha = cursor.fetchone()

        if not linha:
            return

        cursor.execute("DELETE FROM matches WHERE id = %s;", (id_match,))

        if linha[1] in ("pendente", "aceito"):
            cursor.execute(
                "UPDATE doacoes SET status = 'disponivel' WHERE id = %s AND status = 'reservada';",
                (linha[0],)
            )

    return _transacao(operacao)


def matches_da_ong(id_ong):
    """Matches da ONG com os dados da doacao e do doador (o contato so e exposto pelo service, apos o aceite)."""
    def operacao(cursor):
        cursor.execute(
            """
            SELECT m.id, m.status, m.prioridade, d.alimento, d.categoria, d.quantidade_kg, d.validade,
                   dr.regiao, dr.nome, dr.email, dr.telefone
            FROM matches m
            JOIN doacoes d ON d.id = m.doacao_id
            JOIN doadores dr ON dr.id = d.doador_id
            WHERE m.ong_id = %s
            ORDER BY m.id DESC;
            """,
            (id_ong,)
        )
        return cursor.fetchall()

    return _transacao(operacao)


def obter_versao_link(id_ong):
    def operacao(cursor):
        cursor.execute("SELECT versao FROM ong_links_acesso WHERE ong_id = %s;", (id_ong,))
        linha = cursor.fetchone()
        return linha[0] if linha else 1

    return _transacao(operacao)


def obter_info_link(id_ong):
    """(versao, quando_foi_gerado, ativo). Link nunca renovado (versao 1): gerado_em None, vale desde o cadastro da ONG."""
    def operacao(cursor):
        cursor.execute("SELECT versao, atualizado_em, ativo FROM ong_links_acesso WHERE ong_id = %s;", (id_ong,))
        return cursor.fetchone()

    def sem_a_coluna_ativo(cursor):  # banco sem a migracao 007
        cursor.execute("SELECT versao, atualizado_em, TRUE FROM ong_links_acesso WHERE ong_id = %s;", (id_ong,))
        return cursor.fetchone()

    try:
        linha = _transacao(operacao)
    except psycopg.errors.UndefinedColumn:
        linha = _transacao(sem_a_coluna_ativo)

    if not linha:
        return 1, None, True

    return linha[0], (linha[1] if linha[0] > 1 else None), linha[2]


def link_ativo(id_ong):
    """False so quando o gestor desativou o link dessa ONG (ela entra por e-mail e senha)."""
    return obter_info_link(id_ong)[2]


def definir_link_ativo(id_ong, ativo):
    def operacao(cursor):
        cursor.execute(
            """
            INSERT INTO ong_links_acesso (ong_id, versao, ativo) VALUES (%s, 1, %s)
            ON CONFLICT (ong_id) DO UPDATE SET ativo = EXCLUDED.ativo;
            """,
            (id_ong, ativo)
        )

    return _transacao(operacao)


def renovar_link(id_ong):
    """Invalida o link atual da ONG (versao + 1), reativa o link e devolve (nova versao, momento da renovacao)."""
    def operacao(cursor):
        cursor.execute(
            """
            INSERT INTO ong_links_acesso (ong_id, versao, ativo) VALUES (%s, 2, TRUE)
            ON CONFLICT (ong_id) DO UPDATE
                SET versao = ong_links_acesso.versao + 1, atualizado_em = now(), ativo = TRUE
            RETURNING versao, atualizado_em;
            """,
            (id_ong,)
        )
        linha = cursor.fetchone()
        return linha[0], linha[1]

    def sem_a_coluna_ativo(cursor):  # banco sem a migracao 007
        cursor.execute(
            """
            INSERT INTO ong_links_acesso (ong_id, versao) VALUES (%s, 2)
            ON CONFLICT (ong_id) DO UPDATE SET versao = ong_links_acesso.versao + 1, atualizado_em = now()
            RETURNING versao, atualizado_em;
            """,
            (id_ong,)
        )
        linha = cursor.fetchone()
        return linha[0], linha[1]

    try:
        return _transacao(operacao)
    except psycopg.errors.UndefinedColumn:
        return _transacao(sem_a_coluna_ativo)
