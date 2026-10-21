"""Classificacao de risco de descarte e recomendacao de ONGs (modelo em ia/)."""
import unicodedata
from datetime import date, datetime

from ia import inferencia
from repositories.doacao_repository import buscar_doacao
from repositories.doador_repository import buscar_coordenadas as buscar_coordenadas_doador, buscar_doador
from repositories.ong_repository import listar_coordenadas as listar_coordenadas_ongs, listar_ongs
from services import geo

# A categoria da doacao e texto livre; o modelo conhece categorias fixas.
CATEGORIAS = [
    ("hortifruti", ("fruta", "verdura", "legume", "hortifruti", "hortali", "vegetal")),
    ("padaria", ("pao", "padaria", "bolo", "biscoito", "massa fresca")),
    ("laticinios", ("laticin", "leite", "queijo", "iogurte")),
    ("carnes", ("carne", "frango", "peixe", "aves", "embutido", "frios")),
    ("prontos", ("pronto", "marmita", "refeicao", "congelad")),
    ("nao_perecivel", ("grao", "cereal", "enlatado", "nao perecivel", "conserva", "arroz", "feijao", "mercearia")),
]
# Sem coordenadas nem cidade reconhecida, a distancia e uma suposicao (documentada): mesma regiao ou nao.
DISTANCIA_MESMA_REGIAO_KM = 5.0
DISTANCIA_OUTRA_REGIAO_KM = 15.0
# O modelo so viu distancias de 0,5 a 25 km (e capacidades de ate ~200 kg): a inferencia leva valores fora dessa faixa
# ao limite dela (ia/inferencia.py), e o resultado avisa quais entradas foram ajustadas.
DISTANCIA_MAXIMA_TREINO_KM = inferencia.faixa_treino().get("distancia_km", (0, 25.0))[1]
PRIORIDADE = {"alto": "alta", "medio": "media", "baixo": "baixa"}
PENALIDADE_RISCO = {"baixo": 0.0, "medio": 0.5, "alto": 1.0}


def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return texto.lower().strip()


def categoria_do_modelo(categoria, alimento=""):
    if categoria in {nome for nome, _ in CATEGORIAS}:
        return categoria
    texto = _normalizar(categoria) + " " + _normalizar(alimento)
    for nome, chaves in CATEGORIAS:
        if any(chave in texto for chave in chaves):
            return nome
    return ""  # categoria desconhecida: one-hot zerado (comportamento do treino)


def classificar_lote(dados):
    """Risco de descarte para um lote informado diretamente (sem banco)."""
    return inferencia.prever(dados)


def _texto_distancia(km, origem):
    if origem == geo.ORIGEM_ESTIMATIVA:
        return "distância estimada por região"
    detalhe = "pelas coordenadas" if origem == geo.ORIGEM_COORDENADAS else "entre os centros das cidades"
    return "a %s km (%s)" % (("%.1f" % km).replace(".", ","), detalhe)


def _dias_ate(validade, hoje):
    if isinstance(validade, datetime):
        validade = validade.date()
    if isinstance(validade, str):
        validade = date.fromisoformat(validade)
    return max(0, (validade - hoje).days)


def _distancia(posicao_doador, ong_lat, ong_lon, ong_regiao, mesma_regiao):
    """(km, origem): linha reta entre coordenadas ou centros de cidade; senao a estimativa fixa por regiao."""
    posicao_ong, origem_ong = geo.resolver_posicao(ong_lat, ong_lon, ong_regiao)
    if posicao_doador[0] and posicao_ong:
        km = geo.distancia_km(posicao_doador[0], posicao_ong)
        if posicao_doador[1] == origem_ong == geo.ORIGEM_COORDENADAS:
            return km, geo.ORIGEM_COORDENADAS
        # Pelo menos um lado so tem a cidade: dentro da mesma cidade nao da para saber a distancia real.
        return max(km, DISTANCIA_MESMA_REGIAO_KM), geo.ORIGEM_CIDADE
    return (DISTANCIA_MESMA_REGIAO_KM if mesma_regiao else DISTANCIA_OUTRA_REGIAO_KM), geo.ORIGEM_ESTIMATIVA


def recomendar_ongs(id_doacao, hoje=None):
    if not isinstance(id_doacao, int) or id_doacao <= 0:
        raise ValueError("ID da doação inválido.")
    doacao = buscar_doacao(id_doacao)
    if not doacao:
        raise ValueError("Doação não encontrada.")
    _, doador_id, alimento, categoria, quantidade, validade, status, _ = doacao
    if status != "disponivel":
        raise ValueError("Apenas doações disponíveis recebem recomendação.")
    doador = buscar_doador(doador_id)
    regiao_doador = _normalizar(doador[4]) if doador else ""
    lat_doador, lon_doador = buscar_coordenadas_doador(doador_id)
    posicao_doador = geo.resolver_posicao(lat_doador, lon_doador, doador[4] if doador else "")
    coordenadas_ongs = listar_coordenadas_ongs()
    quantidade = float(quantidade)
    dias = _dias_ate(validade, hoje or date.today())
    modelo_cat = categoria_do_modelo(categoria, alimento)

    candidatas = []
    for ong_id, nome, _email, _telefone, regiao, capacidade in listar_ongs():
        capacidade = float(capacidade or 0)
        if capacidade < quantidade:
            continue  # elegibilidade: a ONG precisa comportar o lote
        mesma = bool(regiao_doador) and _normalizar(regiao) == regiao_doador
        lat_ong, lon_ong = coordenadas_ongs.get(ong_id, (None, None))
        distancia, origem_distancia = _distancia(posicao_doador, lat_ong, lon_ong, regiao, mesma)
        resultado = inferencia.prever({
            "alimento_descricao": str(alimento),
            "categoria": modelo_cat,
            "quantidade_kg": quantidade,
            "dias_ate_validade": dias,
            "distancia_km": distancia,
            "capacidade_disponivel_kg": capacidade,
        })
        p = resultado["probabilidades"]
        penalidade = sum(PENALIDADE_RISCO[c] * v for c, v in p.items())
        candidatas.append({
            "ong_id": ong_id,
            "ong_nome": nome,
            "regiao": regiao,
            "capacidade_kg": capacidade,
            "score_ia": round(max(0.0, min(1.0, 1 - penalidade)), 4),
            "risco_descarte": resultado["risco_descarte"],
            "probabilidades": p,
            "mesma_regiao": mesma,
            "distancia_km": round(distancia, 1),
            "distancia_origem": origem_distancia,
            "distancia_acima_da_faixa_do_modelo": distancia > DISTANCIA_MAXIMA_TREINO_KM,
            "entradas_ajustadas_ao_treino": resultado["entradas_ajustadas"],
            "motivo": "capacidade suficiente%s; %s; risco de descarte %s no modelo"
                      % (", mesma região" if mesma else "", _texto_distancia(distancia, origem_distancia),
                         resultado["risco_descarte"]),
        })
    # Empate de score: a ONG mais perto vem primeiro (o modelo so enxerga distancias ate 25 km).
    candidatas.sort(key=lambda c: (-c["score_ia"], c["distancia_km"], c["ong_id"]))
    melhor = candidatas[0]["risco_descarte"] if candidatas else None
    return {
        "doacao_id": id_doacao,
        "dias_ate_validade": dias,
        "prioridade_sugerida": PRIORIDADE.get(melhor),
        "recomendacoes": candidatas[:5],
        "aviso": "Score do modelo treinado com dados simulados. Valores além do que o modelo viu no treino (distância "
                 "acima de 25 km, capacidade acima de ~200 kg) contam como o limite da faixa. Distância em linha reta: "
                 "pelas coordenadas, pelo centro da cidade ou, na falta, estimada por região; não é rota. "
                 "Requer confirmação humana antes de coletar ou receber o alimento.",
    }
