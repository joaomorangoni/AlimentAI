"""Inferencia local do risco de descarte.

Uso: python predict.py '{"alimento_descricao":"pao frances","categoria":"padaria",
"quantidade_kg":20,"dias_ate_validade":1,"distancia_km":4,"capacidade_disponivel_kg":50}'
"""
import json
import sys
from pathlib import Path

import joblib
import pandas as pd

MODEL_PATH = Path(__file__).parent / "models" / "risco_descarte.joblib"


def prever(lote: dict) -> dict:
    # joblib carrega via pickle: so abra modelos gerados por este projeto
    artefato = joblib.load(MODEL_PATH)
    pipe = artefato["pipeline"]
    X = pd.DataFrame([lote])[artefato["features"]]
    probas = pipe.predict_proba(X)[0]
    classes = list(pipe.classes_)
    return {
        "risco_descarte": classes[probas.argmax()],
        "probabilidades": {c: round(float(p), 4) for c, p in zip(classes, probas)},
        "versao_modelo": artefato["versao"],
    }


if __name__ == "__main__":
    entrada = json.loads(sys.argv[1]) if len(sys.argv) > 1 else json.load(sys.stdin)
    print(json.dumps(prever(entrada), ensure_ascii=False, indent=2))
