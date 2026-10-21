"""Treina e avalia o classificador de risco de descarte de lotes.

Compara baseline (classe majoritaria) com LogisticRegression e RandomForest.
Escolha do modelo pelo F1 macro na validacao; metricas finais no teste.
Uso: python train.py
"""
import json
import time
from pathlib import Path

import joblib
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

SEED = 42
BASE = Path(__file__).parent
NUM = ["quantidade_kg", "dias_ate_validade", "distancia_km", "capacidade_disponivel_kg"]
CAT = ["categoria"]
TXT = "alimento_descricao"
ALVO = "risco_descarte"
LABELS = ["baixo", "medio", "alto"]


def preprocess() -> ColumnTransformer:
    return ColumnTransformer(
        [
            ("num", StandardScaler(), NUM),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CAT),
            ("txt", TfidfVectorizer(ngram_range=(1, 2), min_df=2), TXT),
        ]
    )


def candidatos() -> dict:
    return {
        "baseline_majoritaria": DummyClassifier(strategy="most_frequent"),
        "logistic_regression": LogisticRegression(max_iter=1000, random_state=SEED),
        "logistic_regression_balanced": LogisticRegression(max_iter=1000, class_weight="balanced", random_state=SEED),
        "random_forest": RandomForestClassifier(n_estimators=200, min_samples_leaf=3, random_state=SEED, n_jobs=-1),
    }


def exportar_json(pipe: Pipeline, X_treino: pd.DataFrame) -> dict:
    """Serializa o pipeline (scaler + one-hot + TF-IDF + regressao logistica) em JSON puro.

    Inclui a faixa de cada variavel numerica no treino: a API usa para nao extrapolar o modelo fora do que ele viu."""
    prep, clf = pipe.named_steps["prep"], pipe.named_steps["clf"]
    scaler = prep.named_transformers_["num"]
    onehot = prep.named_transformers_["cat"]
    tfidf = prep.named_transformers_["txt"]
    vocab = {termo: int(i) for termo, i in tfidf.vocabulary_.items()}
    return {
        "versao": "1.0.0",
        "classes": [str(c) for c in clf.classes_],
        "numericas": NUM,
        "media": scaler.mean_.tolist(),
        "escala": scaler.scale_.tolist(),
        "categorias": [str(c) for c in onehot.categories_[0]],
        "vocabulario": vocab,
        "idf": tfidf.idf_.tolist(),
        "coef": clf.coef_.tolist(),
        "intercepto": clf.intercept_.tolist(),
        "faixa_treino": {c: [float(X_treino[c].min()), float(X_treino[c].max())] for c in NUM},
    }


def main() -> None:
    df = pd.read_csv(BASE / "data" / "lotes_simulados.csv")
    # cada linha e um lote unico (lote_id nao se repete): sem vazamento por grupo
    if not df["lote_id"].is_unique:
        raise ValueError("lote_id duplicado: risco de vazamento entre treino e teste")
    X, y = df[NUM + CAT + [TXT]], df[ALVO]
    X_tmp, X_te, y_tmp, y_te = train_test_split(X, y, test_size=0.15, stratify=y, random_state=SEED)
    X_tr, X_va, y_tr, y_va = train_test_split(X_tmp, y_tmp, test_size=0.1765, stratify=y_tmp, random_state=SEED)

    resultados, modelos = {}, {}
    for nome, clf in candidatos().items():
        pipe = Pipeline([("prep", preprocess()), ("clf", clf)]).fit(X_tr, y_tr)
        pred = pipe.predict(X_va)
        resultados[nome] = {
            "acuracia_validacao": round(accuracy_score(y_va, pred), 4),
            "f1_macro_validacao": round(f1_score(y_va, pred, average="macro"), 4),
        }
        modelos[nome] = pipe

    # Apenas regressao logistica e exportavel para JSON (inferencia sem pickle nem scikit-learn na API).
    escolhido = max(
        (n for n in modelos if n.startswith("logistic")),
        key=lambda n: resultados[n]["f1_macro_validacao"],
    )
    modelo = modelos[escolhido]

    t0 = time.perf_counter()
    pred = modelo.predict(X_te)
    latencia_ms = (time.perf_counter() - t0) / len(X_te) * 1000
    base_pred = modelos["baseline_majoritaria"].predict(X_te)
    relatorio = classification_report(y_te, pred, labels=LABELS, output_dict=True, zero_division=0)

    metricas = {
        "dataset": {"linhas": len(df), "origem": "simulado", "treino": len(X_tr), "validacao": len(X_va), "teste": len(X_te)},
        "seed": SEED,
        "versao_sklearn": sklearn.__version__,
        "comparacao_validacao": resultados,
        "modelo_escolhido": escolhido,
        "teste": {
            "acuracia": round(accuracy_score(y_te, pred), 4),
            "f1_macro": round(f1_score(y_te, pred, average="macro"), 4),
            "recall_alto_risco": round(relatorio["alto"]["recall"], 4),
            "precisao_alto_risco": round(relatorio["alto"]["precision"], 4),
            "acuracia_baseline": round(accuracy_score(y_te, base_pred), 4),
            "latencia_media_ms_por_lote": round(latencia_ms, 4),
            "matriz_confusao": {"labels": LABELS, "valores": confusion_matrix(y_te, pred, labels=LABELS).tolist()},
            "por_classe": {k: {m: round(v, 4) for m, v in relatorio[k].items()} for k in LABELS},
        },
        "limitacoes": "Dados simulados por regra com ruído; métricas não indicam desempenho em cenário real.",
    }
    (BASE / "models").mkdir(exist_ok=True)
    (BASE / "reports").mkdir(exist_ok=True)
    joblib.dump({"pipeline": modelo, "labels": LABELS, "versao": "1.0.0", "features": NUM + CAT + [TXT]}, BASE / "models" / "risco_descarte.joblib")
    texto = json.dumps(metricas, indent=2, ensure_ascii=False)
    (BASE / "reports" / "metricas.json").write_text(texto, encoding="utf-8")
    destino = BASE.parent / "rede-alimenta-back" / "ia"
    destino.mkdir(exist_ok=True)
    (destino / "metricas.json").write_text(texto, encoding="utf-8")
    (destino / "modelo_risco.json").write_text(json.dumps(exportar_json(modelo, X_tr), ensure_ascii=False), encoding="utf-8")
    print(json.dumps(metricas, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
