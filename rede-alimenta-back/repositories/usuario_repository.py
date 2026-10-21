"""Contas individuais (gestor e ONG), sessoes e auditoria. SQL parametrizado; as regras ficam em autenticacao_service."""
from repositories.fluxo_repository import _transacao

_USUARIO = """
    SELECT u.id, u.perfil, u.ong_id, u.nome, u.email, u.ativo, u.trocar_senha, o.nome, u.ultimo_acesso, u.criado_em
    FROM usuarios u LEFT JOIN ongs o ON o.id = u.ong_id
"""


def criar(perfil, ong_id, nome, email, senha_hash, trocar_senha):
    def operacao(cursor):
        cursor.execute(
            """
            INSERT INTO usuarios (perfil, ong_id, nome, email, senha_hash, trocar_senha)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;
            """,
            (perfil, ong_id, nome, email, senha_hash, trocar_senha)
        )
        return cursor.fetchone()[0]

    return _transacao(operacao)


def buscar_para_login(email):
    """(id, perfil, ong_id, nome, email, ativo, trocar_senha, nome_da_ong, senha_hash) ou None. E-mail sem diferenca de caixa."""
    def operacao(cursor):
        cursor.execute(
            """
            SELECT u.id, u.perfil, u.ong_id, u.nome, u.email, u.ativo, u.trocar_senha, o.nome, u.senha_hash
            FROM usuarios u LEFT JOIN ongs o ON o.id = u.ong_id
            WHERE lower(u.email) = lower(%s);
            """,
            (email,)
        )
        return cursor.fetchone()

    return _transacao(operacao)


def buscar(id_usuario):
    def operacao(cursor):
        cursor.execute(_USUARIO + " WHERE u.id = %s;", (id_usuario,))
        return cursor.fetchone()

    return _transacao(operacao)


def senha_hash_de(id_usuario):
    def operacao(cursor):
        cursor.execute("SELECT senha_hash FROM usuarios WHERE id = %s;", (id_usuario,))
        linha = cursor.fetchone()
        return linha[0] if linha else None

    return _transacao(operacao)


def listar():
    def operacao(cursor):
        cursor.execute(_USUARIO + " ORDER BY u.perfil, lower(u.nome), u.id;")
        return cursor.fetchall()

    return _transacao(operacao)


def contar_ativos(perfil, ong_id=None):
    def operacao(cursor):
        if ong_id is None:
            cursor.execute("SELECT count(*) FROM usuarios WHERE perfil = %s AND ativo;", (perfil,))
        else:
            cursor.execute("SELECT count(*) FROM usuarios WHERE perfil = %s AND ong_id = %s AND ativo;", (perfil, ong_id))
        return cursor.fetchone()[0]

    return _transacao(operacao)


def atualizar_senha(id_usuario, senha_hash, trocar_senha):
    def operacao(cursor):
        cursor.execute(
            "UPDATE usuarios SET senha_hash = %s, trocar_senha = %s WHERE id = %s;",
            (senha_hash, trocar_senha, id_usuario)
        )
        return cursor.rowcount == 1

    return _transacao(operacao)


def definir_ativo(id_usuario, ativo):
    """Ativa ou desativa a conta; desativar encerra as sessoes abertas na mesma transacao."""
    def operacao(cursor):
        cursor.execute("UPDATE usuarios SET ativo = %s WHERE id = %s;", (ativo, id_usuario))
        mudou = cursor.rowcount == 1

        if mudou and not ativo:
            cursor.execute("DELETE FROM usuario_sessoes WHERE usuario_id = %s;", (id_usuario,))

        return mudou

    return _transacao(operacao)


def registrar_acesso(id_usuario):
    def operacao(cursor):
        cursor.execute("UPDATE usuarios SET ultimo_acesso = now() WHERE id = %s;", (id_usuario,))

    return _transacao(operacao)


# --- sessoes -------------------------------------------------------------------------------------------------------
def criar_sessao(id_usuario, token_hash, segundos):
    def operacao(cursor):
        cursor.execute("DELETE FROM usuario_sessoes WHERE expira_em < now();")  # faxina das vencidas
        cursor.execute(
            "INSERT INTO usuario_sessoes (token_hash, usuario_id, expira_em) VALUES (%s, %s, now() + make_interval(secs => %s));",
            (token_hash, id_usuario, segundos)
        )

    return _transacao(operacao)


def buscar_sessao(token_hash):
    """(id, perfil, ong_id, nome, email, ativo, trocar_senha, nome_da_ong) da sessao valida, ou None."""
    def operacao(cursor):
        cursor.execute(
            """
            SELECT u.id, u.perfil, u.ong_id, u.nome, u.email, u.ativo, u.trocar_senha, o.nome
            FROM usuario_sessoes s
            JOIN usuarios u ON u.id = s.usuario_id
            LEFT JOIN ongs o ON o.id = u.ong_id
            WHERE s.token_hash = %s AND s.expira_em > now();
            """,
            (token_hash,)
        )
        return cursor.fetchone()

    return _transacao(operacao)


def apagar_sessao(token_hash):
    def operacao(cursor):
        cursor.execute("DELETE FROM usuario_sessoes WHERE token_hash = %s;", (token_hash,))

    return _transacao(operacao)


def apagar_sessoes_do_usuario(id_usuario, manter_hash=None):
    def operacao(cursor):
        cursor.execute(
            "DELETE FROM usuario_sessoes WHERE usuario_id = %s AND token_hash <> %s;",
            (id_usuario, manter_hash or "")
        )

    return _transacao(operacao)


# --- auditoria -----------------------------------------------------------------------------------------------------
def registrar_auditoria(ator_tipo, ator_id, ator_nome, acao, recurso, registro_id, ip):
    def operacao(cursor):
        cursor.execute(
            """
            INSERT INTO auditoria_acoes (ator_tipo, ator_id, ator_nome, acao, recurso, registro_id, ip)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
            """,
            (ator_tipo, ator_id, ator_nome, acao, recurso, registro_id, ip)
        )

    return _transacao(operacao)


def listar_auditoria(limite):
    def operacao(cursor):
        cursor.execute(
            "SELECT id, quando, ator_tipo, ator_nome, acao, recurso, registro_id FROM auditoria_acoes ORDER BY id DESC LIMIT %s;",
            (limite,)
        )
        return cursor.fetchall()

    return _transacao(operacao)
