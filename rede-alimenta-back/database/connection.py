import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def conectar():
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL não encontrada no arquivo .env")

    # connect_timeout: com o banco fora do ar o pedido (ou o inicio do servidor) falha em segundos, nao fica pendurado.
    return psycopg.connect(DATABASE_URL, connect_timeout=10)


def testar_conexao():
    try:
        conexao = conectar()

        with conexao.cursor() as cursor:
            cursor.execute("SELECT current_database();")
            banco = cursor.fetchone()

        conexao.close()

        print("Conexão com o Supabase realizada com sucesso!")
        print("Banco:", banco[0])

    except Exception as erro:
        print("Erro ao conectar ao banco:")
        print(erro)


if __name__ == "__main__":
    testar_conexao()