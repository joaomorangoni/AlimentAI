"""Dados DE DEMONSTRACAO para o dashboard (kg salvos, refeicoes por regiao, mapa, tempo de match). Uso:

    python demo_seed.py            # cria os dados (so em banco local)
    python demo_seed.py --limpar   # remove somente o que este script criou

Tudo que o script cria usa e-mails @demo.alimenta.example (e codigos de acompanhamento que comecam com "demo-"), entao a
limpeza nunca toca em dados reais. Por seguranca, recusa-se a rodar em banco que nao seja local, a menos que se passe
--confirmo-nuvem."""
import hashlib
import random
import sys
from datetime import datetime, timedelta
from urllib.parse import urlparse

import migrar
from database.connection import DATABASE_URL, conectar

DOMINIO = "@demo.alimenta.example"
SEMENTE = 2026
REGIOES = {"São Paulo": (-23.55, -46.63), "Campinas": (-22.91, -47.06), "Santos": (-23.96, -46.33),
           "Sorocaba": (-23.50, -47.46), "Guarulhos": (-23.46, -46.53)}
DOADORES = ["Padaria Pão Quente", "Mercado Bom Preço", "Sítio Verde", "Restaurante Sabor Caseiro", "Hortifruti Central", "Laticínios Serra Azul"]
ONGS = [("Banco de Alimentos Campinas", "Campinas", 2000), ("Instituto Boa Mesa", "Santos", 300),
        ("Casa Acolher", "São Paulo", 800), ("Mesa Cheia Sorocaba", "Sorocaba", 150), ("Cozinha Solidária Guarulhos", "Guarulhos", 500)]
ALIMENTOS = [("Pão francês", "padaria"), ("Tomate", "hortifruti"), ("Banana", "hortifruti"), ("Leite longa vida", "laticinios"),
             ("Arroz", "nao_perecivel"), ("Feijão", "nao_perecivel"), ("Frango congelado", "carnes"), ("Marmita pronta", "prontos")]


def codigo_demo(n):
    return f"demo-oferta-{n:03d}-acompanhar"


def hash_codigo(codigo):
    return hashlib.sha256(codigo.encode()).hexdigest()


def com_variacao(rng, regiao):
    """Posicao um pouco diferente do centro da cidade (cerca de 3 km), para doadores e ONGs nao ficarem no mesmo ponto."""
    lat, lon = REGIOES[regiao]
    return round(lat + rng.uniform(-0.03, 0.03), 6), round(lon + rng.uniform(-0.03, 0.03), 6)


def banco_local():
    host = urlparse(DATABASE_URL or "").hostname or ""
    return host in ("localhost", "127.0.0.1", "::1", "db", "postgres")


def limpar(cursor):
    padrao = "%" + DOMINIO
    cursor.execute("DELETE FROM ofertas_publicas WHERE codigo_hash = ANY(%s);", ([hash_codigo(codigo_demo(n)) for n in range(1, 201)],))
    cursor.execute("DELETE FROM matches WHERE ong_id IN (SELECT id FROM ongs WHERE email LIKE %s);", (padrao,))
    cursor.execute("DELETE FROM doacoes WHERE doador_id IN (SELECT id FROM doadores WHERE email LIKE %s);", (padrao,))
    cursor.execute("DELETE FROM doadores WHERE email LIKE %s;", (padrao,))
    cursor.execute("DELETE FROM ongs WHERE email LIKE %s;", (padrao,))


def popular(cursor):
    rng = random.Random(SEMENTE)  # nosec B311 - dados de demonstracao reproduziveis, sem fim criptografico
    agora = datetime.now().replace(microsecond=0)
    nomes_regiao = list(REGIOES)
    doadores = []
    for i, nome in enumerate(DOADORES):
        regiao = nomes_regiao[i % len(nomes_regiao)]
        lat, lon = com_variacao(rng, regiao)
        email = f"doador{i + 1}{DOMINIO}"
        cursor.execute(
            "INSERT INTO doadores (nome, email, telefone, regiao, latitude, longitude) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;",
            (nome, email, "(11) 91234-5678", regiao, lat, lon))
        doadores.append((cursor.fetchone()[0], nome, email, regiao))
    ongs = []
    for i, (nome, regiao, capacidade) in enumerate(ONGS):
        lat, lon = com_variacao(rng, regiao)
        cursor.execute(
            "INSERT INTO ongs (nome, email, telefone, regiao, latitude, longitude, capacidade_kg) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;",
            (nome, f"ong{i + 1}{DOMINIO}", "(11) 3333-4444", regiao, lat, lon, capacidade))
        ongs.append(cursor.fetchone()[0])

    ofertas = 0
    for n in range(48):
        alimento, categoria = rng.choice(ALIMENTOS)
        cadastro = agora - timedelta(days=rng.randint(1, 60), hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
        kg = rng.choice([8, 12, 20, 35, 50, 80, 120, 200])
        sorteio = n % 8
        if sorteio < 5:
            status = "concluida"
        elif sorteio == 5:
            status = "reservada"
        elif sorteio == 6:
            status = "disponivel"
        else:
            status = "cancelada"
        validade = (agora + timedelta(days=rng.randint(0, 3) if status == "disponivel" and n % 16 == 6 else rng.randint(5, 40))).date()
        doador_id, doador_nome, doador_email, doador_regiao = rng.choice(doadores)
        cursor.execute(
            "INSERT INTO doacoes (doador_id, alimento, categoria, quantidade_kg, validade, status, data_cadastro) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;",
            (doador_id, alimento, categoria, kg, validade, status, cadastro))
        doacao_id = cursor.fetchone()[0]
        match_id = None
        if status in ("concluida", "reservada"):
            data_match = cadastro + timedelta(minutes=rng.randint(25, 60 * 20))
            cursor.execute(
                "INSERT INTO matches (doacao_id, ong_id, score_ia, prioridade, status, data_match) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;",
                (doacao_id, rng.choice(ongs), round(rng.uniform(0.62, 0.99), 4), rng.choice(["baixa", "media", "alta"]),
                 "concluido" if status == "concluida" else "aceito", data_match))
            match_id = cursor.fetchone()[0]
        if match_id and status == "concluida":
            # 4 em cada 5 entregas confirmadas pela propria ONG, as demais pelo gestor.
            cursor.execute("INSERT INTO match_confirmacoes (match_id, origem, confirmado_em) VALUES (%s, %s, %s);",
                           (match_id, "gestor" if n % 5 == 0 else "ong", data_match + timedelta(hours=rng.randint(1, 30))))
        if n % 2 == 0 and status != "cancelada":
            # Metade das doacoes veio de ofertas da pagina publica: o doador enviou horas antes da aprovacao.
            ofertas += 1
            cursor.execute(
                """INSERT INTO ofertas_publicas (codigo_hash, nome, email, telefone, regiao, alimento, categoria, quantidade_kg,
                                                 validade, status, doacao_id, criado_em, decidido_em)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'aprovada', %s, %s, %s);""",
                (hash_codigo(codigo_demo(ofertas)), doador_nome, doador_email, "(11) 91234-5678", doador_regiao, alimento, categoria,
                 kg, validade, doacao_id, cadastro - timedelta(hours=rng.randint(1, 10)), cadastro))

    # Ofertas ainda em analise (aparecem na fila do gestor) e uma recusada (dados pessoais ja apagados).
    for i, (alimento, categoria, kg) in enumerate([("Tomate", "hortifruti", 15), ("Pão francês", "padaria", 30)], start=1):
        ofertas += 1
        cursor.execute(
            """INSERT INTO ofertas_publicas (codigo_hash, nome, email, telefone, regiao, alimento, categoria, quantidade_kg, validade, criado_em)
               VALUES (%s, %s, %s, NULL, %s, %s, %s, %s, %s, %s);""",
            (hash_codigo(codigo_demo(ofertas)), f"Visitante de demonstração {i}", f"visitante{i}{DOMINIO}", "Campinas", alimento, categoria,
             kg, (agora + timedelta(days=4)).date(), agora - timedelta(hours=i)))
    ofertas += 1
    cursor.execute(
        """INSERT INTO ofertas_publicas (codigo_hash, nome, email, telefone, regiao, alimento, categoria, quantidade_kg, validade,
                                         status, criado_em, decidido_em)
           VALUES (%s, '(removido)', %s, NULL, NULL, 'Biscoito', 'padaria', 5, %s, 'recusada', %s, %s);""",
        (hash_codigo(codigo_demo(ofertas)), f"removido-demo-{ofertas}@invalido", (agora + timedelta(days=30)).date(),
         agora - timedelta(days=2), agora - timedelta(days=1)))
    return ofertas


def main():
    if not banco_local() and "--confirmo-nuvem" not in sys.argv:
        sys.exit("DATABASE_URL nao e um banco local. Este script cria dados de demonstracao; "
                 "para usa-lo na nuvem, passe --confirmo-nuvem (e depois remova com --limpar).")
    migrar.aplicar()  # garante as tabelas de ofertas e de confirmacoes
    conexao = conectar()
    try:
        with conexao.cursor() as cursor:
            limpar(cursor)
            ofertas = 0 if "--limpar" in sys.argv else popular(cursor)
        conexao.commit()
        if "--limpar" in sys.argv:
            print("Dados de demonstracao removidos.")
        else:
            print("Dados de demonstracao criados (e-mails " + DOMINIO + ").")
            print("Codigos de acompanhamento de exemplo (abra /acompanhar#CODIGO):")
            for n in (ofertas - 2, ofertas - 1, ofertas, 1):
                print("  ", codigo_demo(n))
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()


if __name__ == "__main__":
    main()
