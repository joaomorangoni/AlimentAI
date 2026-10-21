"""Inferencia do risco de descarte em Python puro, a partir de modelo_risco.json.

Reproduz o pipeline treinado em ml/train.py (padronizacao + one-hot + TF-IDF +
regressao logistica) sem scikit-learn e sem pickle: o artefato e apenas dados.
"""
import json
import math
import re
from pathlib import Path

MODELO_PATH = Path(__file__).parent / "modelo_risco.json"
METRICAS_PATH = Path(__file__).parent / "metricas.json"
TOKEN = re.compile(r"(?u)\b\w\w+\b")  # mesmo padrao do TfidfVectorizer

# faixa aceita pela API: protege contra entradas absurdas e nao finitas
LIMITES = {
    "quantidade_kg": (0.01, 100000),
    "dias_ate_validade": (0, 3650),
    "distancia_km": (0, 5000),
    "capacidade_disponivel_kg": (0, 1000000),
}
MAX_TEXTO = 200

_cache = {}


def _modelo():
    if "modelo" not in _cache:
        _cache["modelo"] = json.loads(MODELO_PATH.read_text(encoding="utf-8"))
    return _cache["modelo"]


def faixa_treino():
    """{variavel: [minimo, maximo]} vistos no treino ({} se o modelo nao traz a faixa)."""
    return _modelo().get("faixa_treino") or {}


def metricas():
    """Metricas do ultimo treino (conjunto de teste, dados simulados)."""
    if "metricas" not in _cache:
        _cache["metricas"] = json.loads(METRICAS_PATH.read_text(encoding="utf-8"))
    return _cache["metricas"]


def validar(lote):
    if not isinstance(lote, dict):
        raise ValueError("Envie um objeto JSON.")
    limpo = {}
    texto = lote.get("alimento_descricao")
    if not isinstance(texto, str) or not texto.strip() or len(texto) > MAX_TEXTO:
        raise ValueError("alimento_descricao deve ser texto de 1 a %d caracteres." % MAX_TEXTO)
    limpo["alimento_descricao"] = texto
    categoria = lote.get("categoria")
    if not isinstance(categoria, str) or len(categoria) > 60:
        raise ValueError("categoria deve ser texto de até 60 caracteres.")
    limpo["categoria"] = categoria
    for campo, (minimo, maximo) in LIMITES.items():
        valor = lote.get(campo)
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
            raise ValueError("%s deve ser um número." % campo)
        if not minimo <= valor <= maximo:
            raise ValueError("%s deve estar entre %s e %s." % (campo, minimo, maximo))
        limpo[campo] = float(valor)
    return limpo


def _ngramas(texto):
    tokens = TOKEN.findall(texto.lower())
    return tokens + [a + " " + b for a, b in zip(tokens, tokens[1:])]


def _ajustar_a_faixa(x, faixa):
    """Leva cada numero para dentro da faixa vista no treino (regressao logistica extrapola sem limite fora dela).

    Devolve os nomes das variaveis que foram ajustadas, para quem chama poder avisar."""
    ajustadas = []
    for campo, (minimo, maximo) in faixa.items():
        if campo in x and not minimo <= x[campo] <= maximo:
            x[campo] = min(max(x[campo], minimo), maximo)
            ajustadas.append(campo)
    return ajustadas


def prever(lote):
    """Retorna {'risco_descarte', 'probabilidades', 'versao_modelo', 'entradas_ajustadas'} para um lote valido.

    Valores fora da faixa do treino (ex.: ONG com capacidade de 2.000 kg quando o modelo viu ate 200) sao levados ao
    limite da faixa, e `entradas_ajustadas` lista quais foram."""
    m = _modelo()
    x = validar(lote)
    ajustadas = _ajustar_a_faixa(x, m.get("faixa_treino") or {})
    atributos = [(x[c] - mu) / sc for c, mu, sc in zip(m["numericas"], m["media"], m["escala"])]
    atributos += [1.0 if x["categoria"] == c else 0.0 for c in m["categorias"]]
    tfidf = [0.0] * len(m["idf"])
    for termo in _ngramas(x["alimento_descricao"]):
        i = m["vocabulario"].get(termo)
        if i is not None:
            tfidf[i] += m["idf"][i]
    norma = math.sqrt(sum(v * v for v in tfidf))
    atributos += [v / norma for v in tfidf] if norma else tfidf
    scores = [sum(w * a for w, a in zip(pesos, atributos)) + b for pesos, b in zip(m["coef"], m["intercepto"])]
    maior = max(scores)
    exps = [math.exp(s - maior) for s in scores]
    total = sum(exps)
    probas = {c: round(e / total, 4) for c, e in zip(m["classes"], exps)}
    return {
        "risco_descarte": max(probas, key=probas.get),
        "probabilidades": probas,
        "versao_modelo": m["versao"],
        "entradas_ajustadas": ajustadas,
    }
