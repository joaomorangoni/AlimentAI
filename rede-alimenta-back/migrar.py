"""Aplica o esquema base (database/schema.sql) e as migracoes de migracoes/ (idempotentes e aditivas).

Uso manual: python migrar.py. O servidor tambem chama aplicar() ao iniciar (desligue com AUTO_MIGRAR=0)."""
from pathlib import Path

from database.connection import conectar

BASE = Path(__file__).resolve().parent
# Ao iniciar o servidor, nunca esperar sem limite: se outra sessao segurar a tabela ou o banco estiver lento, falha e segue.
LIMITES = "SET LOCAL lock_timeout = '5s'; SET LOCAL statement_timeout = '60s';\n"


def arquivos():
    return [BASE / "database" / "schema.sql", *sorted((BASE / "migracoes").glob("*.sql"))]


def aplicar(conexao=None):
    """Roda cada arquivo em sua propria transacao e devolve os nomes aplicados. Nunca apaga nem altera dados."""
    propria = conexao is None
    conexao = conexao or conectar()
    aplicadas = []
    try:
        for arquivo in arquivos():
            with conexao.cursor() as cursor:
                cursor.execute(LIMITES + arquivo.read_text(encoding="utf-8"))
            conexao.commit()
            aplicadas.append(arquivo.name)
        return aplicadas
    except Exception:
        conexao.rollback()
        raise
    finally:
        if propria:
            conexao.close()


def main():
    for nome in aplicar():
        print("aplicada:", nome)


if __name__ == "__main__":
    main()
