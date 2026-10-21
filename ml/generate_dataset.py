"""Gera o dataset SIMULADO de lotes de alimentos (sem dados pessoais).

Uso: python generate_dataset.py
Saida: data/lotes_simulados.csv
"""
import random
from pathlib import Path

import pandas as pd

SEED = 42
N = 3000
DATA_DIR = Path(__file__).parent / "data"

# categoria: (itens, perecibilidade 0-1; maior = estraga mais rapido, validade tipica em dias)
CATEGORIAS = {
    "hortifruti": (["tomate maduro", "alface", "banana", "cenoura", "mamao", "couve"], 0.9, 5),
    "padaria": (["pao frances", "bolo simples", "pao de forma", "rosca"], 0.8, 3),
    "laticinios": (["leite integral", "iogurte natural", "queijo minas", "requeijao"], 0.7, 10),
    "carnes": (["frango resfriado", "carne moida", "linguica", "peixe fresco"], 0.95, 4),
    "prontos": (["marmita pronta", "sopa pronta", "lasanha congelada"], 0.85, 3),
    "nao_perecivel": (["arroz 5kg", "feijao", "macarrao", "oleo de soja", "farinha de trigo"], 0.1, 180),
}
QUALIFICADORES = ["", "", "embalado", "a granel", "caixa lacrada", "sobra do dia", "proximo do vencimento"]
OBS = ["origem_dados"]


def risco(perecibilidade: float, dias: float, dist: float, cap_ratio: float, rng: random.Random) -> str:
    """Rotulo por regra com ruido. Documentado: o modelo aprende uma regra
    simulada, nao comprova eficacia em cenario real."""
    score = (
        2.2 * perecibilidade / max(dias, 0.5) ** 0.5
        + 0.02 * dist
        + 0.6 * (1 - min(cap_ratio, 1.5) / 1.5)
        + rng.gauss(0, 0.18)
    )
    if score > 1.15:
        return "alto"
    if score > 0.6:
        return "medio"
    return "baixo"


def main() -> None:
    rng = random.Random(SEED)  # nosec B311 - simulacao reproduzivel, sem uso criptografico
    rows = []
    for i in range(1, N + 1):
        cat = rng.choice(list(CATEGORIAS))
        itens, perec, validade_tipica = CATEGORIAS[cat]
        desc = " ".join(filter(None, [rng.choice(itens), rng.choice(QUALIFICADORES)]))
        dias = max(0, round(rng.expovariate(1 / validade_tipica) * rng.uniform(0.3, 1.0)))
        if "proximo do vencimento" in desc:
            dias = min(dias, rng.randint(0, 2))
        qtd = round(rng.uniform(1, 120), 1)
        dist = round(rng.uniform(0.5, 25), 1)
        cap = round(rng.uniform(5, 200), 1)
        rows.append(
            {
                "lote_id": f"L{i:05d}",
                "alimento_descricao": desc,
                "categoria": cat,
                "quantidade_kg": qtd,
                "dias_ate_validade": dias,
                "distancia_km": dist,
                "capacidade_disponivel_kg": cap,
                "risco_descarte": risco(perec, dias, dist, cap / qtd, rng),
                "origem_dados": "simulado",
            }
        )
    df = pd.DataFrame(rows)
    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(DATA_DIR / "lotes_simulados.csv", index=False)
    print(df["risco_descarte"].value_counts().to_string())


if __name__ == "__main__":
    main()
