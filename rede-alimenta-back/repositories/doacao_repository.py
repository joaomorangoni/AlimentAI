from database.connection import conectar


def listar_doacoes():
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT
                    d.id,
                    d.doador_id,
                    doador.nome,
                    d.alimento,
                    d.categoria,
                    d.quantidade_kg,
                    d.validade,
                    d.status,
                    d.data_cadastro
                FROM doacoes d
                JOIN doadores doador
                    ON d.doador_id = doador.id
                ORDER BY d.id;
            """)

            return cursor.fetchall()

    finally:
        conexao.close()


def buscar_doacao(id_doacao):
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT
                    id,
                    doador_id,
                    alimento,
                    categoria,
                    quantidade_kg,
                    validade,
                    status,
                    data_cadastro
                FROM doacoes
                WHERE id = %s;
            """, (id_doacao,))

            return cursor.fetchone()

    finally:
        conexao.close()


def cadastrar_doacao(
    doador_id,
    alimento,
    categoria,
    quantidade_kg,
    validade
):
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                INSERT INTO doacoes (
                    doador_id,
                    alimento,
                    categoria,
                    quantidade_kg,
                    validade
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id;
            """, (
                doador_id,
                alimento,
                categoria,
                quantidade_kg,
                validade
            ))

            novo_id = cursor.fetchone()[0]

        conexao.commit()
        return novo_id

    except Exception:
        conexao.rollback()
        raise

    finally:
        conexao.close()


def atualizar_doacao(
    id_doacao,
    alimento,
    categoria,
    quantidade_kg,
    validade,
    status
):
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                UPDATE doacoes
                SET alimento = %s,
                    categoria = %s,
                    quantidade_kg = %s,
                    validade = %s,
                    status = %s
                WHERE id = %s;
            """, (
                alimento,
                categoria,
                quantidade_kg,
                validade,
                status,
                id_doacao
            ))

        conexao.commit()

    except Exception:
        conexao.rollback()
        raise

    finally:
        conexao.close()


def excluir_doacao(id_doacao):
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                DELETE FROM doacoes
                WHERE id = %s;
            """, (id_doacao,))

        conexao.commit()

    except Exception:
        conexao.rollback()
        raise

    finally:
        conexao.close()


if __name__ == "__main__":
    print("DOAÇÕES CADASTRADAS:")
    print("--------------------")

    for doacao in listar_doacoes():
        print(doacao)