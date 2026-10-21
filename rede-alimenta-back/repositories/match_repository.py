import psycopg

from database.connection import conectar


def listar_matches():
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT
                    m.id,
                    m.doacao_id,
                    d.alimento,
                    m.ong_id,
                    o.nome,
                    m.score_ia,
                    m.prioridade,
                    m.status,
                    m.data_match
                FROM matches m
                JOIN doacoes d
                    ON m.doacao_id = d.id
                JOIN ongs o
                    ON m.ong_id = o.id
                ORDER BY m.id;
            """)

            return cursor.fetchall()

    finally:
        conexao.close()


def listar_confirmacoes():
    """{id_do_match: 'ong' | 'gestor'} das entregas concluidas. Vazio se a migracao 006 ainda nao foi aplicada."""
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            try:
                cursor.execute("SELECT match_id, origem FROM match_confirmacoes;")
            except psycopg.errors.UndefinedTable:
                return {}

            return dict(cursor.fetchall())

    finally:
        conexao.close()


def buscar_match(id_match):
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT
                    id,
                    doacao_id,
                    ong_id,
                    score_ia,
                    prioridade,
                    status,
                    data_match
                FROM matches
                WHERE id = %s;
            """, (id_match,))

            return cursor.fetchone()

    finally:
        conexao.close()


def cadastrar_match(
    doacao_id,
    ong_id,
    score_ia,
    prioridade,
    status="pendente"
):
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                INSERT INTO matches (
                    doacao_id,
                    ong_id,
                    score_ia,
                    prioridade,
                    status
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id;
            """, (
                doacao_id,
                ong_id,
                score_ia,
                prioridade,
                status
            ))

            novo_id = cursor.fetchone()[0]

        conexao.commit()
        return novo_id

    except Exception:
        conexao.rollback()
        raise

    finally:
        conexao.close()


def atualizar_status_match(id_match, status):
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                UPDATE matches
                SET status = %s
                WHERE id = %s;
            """, (
                status,
                id_match
            ))

        conexao.commit()

    except Exception:
        conexao.rollback()
        raise

    finally:
        conexao.close()


def excluir_match(id_match):
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                DELETE FROM matches
                WHERE id = %s;
            """, (id_match,))

        conexao.commit()

    except Exception:
        conexao.rollback()
        raise

    finally:
        conexao.close()


if __name__ == "__main__":
    print("MATCHES CADASTRADOS:")
    print("--------------------")

    for match in listar_matches():
        print(match)