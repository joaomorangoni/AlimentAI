"""O modelo JSON (API) deve reproduzir o pipeline scikit-learn. Execute da raiz: python -m unittest discover -s ml/tests"""
import sys
import unittest
from pathlib import Path

import joblib
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "rede-alimenta-back"))
from ia import inferencia  # noqa: E402


class ExportacaoTests(unittest.TestCase):
    def test_json_equivale_ao_pipeline_sklearn(self):
        artefato = joblib.load(RAIZ / "ml" / "models" / "risco_descarte.joblib")
        pipe = artefato["pipeline"]
        df = pd.read_csv(RAIZ / "ml" / "data" / "lotes_simulados.csv").head(400)
        esperado = pipe.predict_proba(df[artefato["features"]])
        classes = list(pipe.classes_)
        for (_, linha), probas in zip(df.iterrows(), esperado):
            lote = {k: (float(linha[k]) if k not in ("alimento_descricao", "categoria") else linha[k]) for k in artefato["features"]}
            obtido = inferencia.prever(lote)["probabilidades"]
            for classe, p in zip(classes, probas):
                self.assertAlmostEqual(obtido[classe], p, places=3)


if __name__ == "__main__":
    unittest.main()
