from database.connection import conectar


def listar_doadores():
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT id, nome, email, telefone, regiao
                FROM doadores
                ORDER BY id;
            """)

            return cursor.fetchall()

    finally:
        conexao.close()


def buscar_doador(id_doador):
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT id, nome, email, telefone, regiao
                FROM doadores
                WHERE id = %s;
            """, (id_doador,))

            return cursor.fetchone()

    finally:
        conexao.close()


def buscar_coordenadas(id_doador):
    """(latitude, longitude) do doador; (None, None) se nao informadas ou se ele nao existir."""
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT latitude, longitude FROM doadores WHERE id = %s;", (id_doador,))
            linha = cursor.fetchone()

            return (linha[0], linha[1]) if linha else (None, None)

    finally:
        conexao.close()


def cadastrar_doador(
    nome,
    email,
    telefone,
    regiao,
    latitude=None,
    longitude=None
):
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                INSERT INTO doadores (
                    nome,
                    email,
                    telefone,
                    regiao,
                    latitude,
                    longitude
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id;
            """, (
                nome,
                email,
                telefone,
                regiao,
                latitude,
                longitude
            ))

            novo_id = cursor.fetchone()[0]

        conexao.commit()

        return novo_id

    except Exception:
        conexao.rollback()
        raise

    finally:
        conexao.close()


def atualizar_doador(id_doador, nome, telefone, regiao):
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                UPDATE doadores
                SET nome = %s,
                    telefone = %s,
                    regiao = %s
                WHERE id = %s;
            """, (
                nome,
                telefone,
                regiao,
                id_doador
            ))

        conexao.commit()

    except Exception:
        conexao.rollback()
        raise

    finally:
        conexao.close()


def excluir_doador(id_doador):
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                DELETE FROM doadores
                WHERE id = %s;
            """, (id_doador,))

        conexao.commit()

    except Exception:
        conexao.rollback()
        raise

    finally:
        conexao.close()


if __name__ == "__main__":

    print("DOADORES CADASTRADOS:")
    print("---------------------")

    for doador in listar_doadores():
        print(doador)