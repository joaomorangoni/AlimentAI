from database.connection import conectar


def listar_ongs():
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT
                    id,
                    nome,
                    email,
                    telefone,
                    regiao,
                    capacidade_kg
                FROM ongs
                ORDER BY id;
            """)

            return cursor.fetchall()

    finally:
        conexao.close()


def listar_coordenadas():
    """{id_da_ong: (latitude, longitude)}; os valores sao None quando a ONG nao informou coordenadas."""
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT id, latitude, longitude FROM ongs;")

            return {id_: (latitude, longitude) for id_, latitude, longitude in cursor.fetchall()}

    finally:
        conexao.close()


def listar_ongs_com_cnpj():
    """Mesmas ONGs de listar_ongs, com o CNPJ no fim de cada linha (o resto do sistema usa a forma sem CNPJ)."""
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT id, nome, email, telefone, regiao, capacidade_kg, cnpj
                FROM ongs
                ORDER BY id;
            """)

            return cursor.fetchall()

    finally:
        conexao.close()


def buscar_ong(id_ong):
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                SELECT
                    id,
                    nome,
                    email,
                    telefone,
                    regiao,
                    capacidade_kg
                FROM ongs
                WHERE id = %s;
            """, (id_ong,))

            return cursor.fetchone()

    finally:
        conexao.close()


def cadastrar_ong(
    nome,
    email,
    telefone,
    regiao,
    capacidade_kg,
    latitude=None,
    longitude=None,
    cnpj=None
):
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            if cnpj:
                cursor.execute("""
                    INSERT INTO ongs (nome, email, telefone, regiao, capacidade_kg, latitude, longitude, cnpj)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (nome, email, telefone, regiao, capacidade_kg, latitude, longitude, cnpj))
            else:
                # Sem CNPJ, o INSERT nao menciona a coluna (funciona mesmo antes da migracao 004).
                cursor.execute("""
                    INSERT INTO ongs (nome, email, telefone, regiao, capacidade_kg, latitude, longitude)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (nome, email, telefone, regiao, capacidade_kg, latitude, longitude))

            novo_id = cursor.fetchone()[0]

        conexao.commit()

        return novo_id

    except Exception:
        conexao.rollback()
        raise

    finally:
        conexao.close()


def atualizar_ong(
    id_ong,
    nome,
    telefone,
    regiao,
    capacidade_kg,
    alterar_cnpj=False,
    cnpj=None
):
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            if alterar_cnpj:
                cursor.execute("""
                    UPDATE ongs
                    SET nome = %s, telefone = %s, regiao = %s, capacidade_kg = %s, cnpj = %s
                    WHERE id = %s;
                """, (nome, telefone, regiao, capacidade_kg, cnpj, id_ong))
            else:
                cursor.execute("""
                    UPDATE ongs
                    SET nome = %s, telefone = %s, regiao = %s, capacidade_kg = %s
                    WHERE id = %s;
                """, (nome, telefone, regiao, capacidade_kg, id_ong))

        conexao.commit()

    except Exception:
        conexao.rollback()
        raise

    finally:
        conexao.close()


def excluir_ong(id_ong):
    conexao = conectar()

    try:
        with conexao.cursor() as cursor:
            cursor.execute("""
                DELETE FROM ongs
                WHERE id = %s;
            """, (id_ong,))

        conexao.commit()

    except Exception:
        conexao.rollback()
        raise

    finally:
        conexao.close()


if __name__ == "__main__":
    print("ONGS CADASTRADAS:")
    print("-----------------")

    for ong in listar_ongs():
        print(ong)