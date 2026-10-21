"""Indicadores do dashboard, calculados a partir dos dados existentes (sem novas consultas SQL)."""
import json
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from ia import inferencia
from repositories.doacao_repository import listar_doacoes
from repositories.doador_repository import listar_doadores
from repositories.match_repository import listar_confirmacoes, listar_matches
from repositories.oferta_repository import inicio_por_doacao
from repositories.ong_repository import listar_coordenadas, listar_ongs
from services import geo

SEGURANCA_PATH = Path(__file__).resolve().parent.parent / "ia" / "seguranca.json"
KG_POR_REFEICAO = 0.5  # suposicao da equipe; apresentar refeicoes como estimativa
DIAS_VALIDADE_CRITICA = 3
STATUS_DOACAO = ("disponivel", "reservada", "concluida", "cancelada")


def _como_datetime(valor):
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None)
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day)
    return None


def _data(valor):
    return valor.date() if isinstance(valor, datetime) else valor


def _mais_cedo(*momentos):
    """O primeiro de varios momentos (ignorando os ausentes), sem fuso."""
    validos = [m for m in map(_como_datetime, momentos) if m]
    return min(validos) if validos else None


def _atendimento_por_regiao(kg_concluidas, matches, ongs, coordenadas):
    """Kg entregues por regiao da ONG que recebeu (onde a carencia foi atendida), com a posicao no mapa quando existe."""
    ong_por_id = {ong[0]: ong for ong in ongs}
    regioes = defaultdict(lambda: {"kg": 0.0, "ongs": set()})
    atribuidas = set()
    for _id, doacao_id, _alimento, ong_id, _ong, _score, _prio, status, _data in matches:
        if status != "concluido" or doacao_id in atribuidas or doacao_id not in kg_concluidas:
            continue
        atribuidas.add(doacao_id)  # cada doacao conta uma vez
        ong = ong_por_id.get(ong_id)
        regiao = str(ong[4]).strip() if ong and ong[4] else "Sem região"
        regioes[regiao]["kg"] += kg_concluidas[doacao_id]
        regioes[regiao]["ongs"].add(ong_id)
    sem_ong = sum(kg for id_, kg in kg_concluidas.items() if id_ not in atribuidas)
    if sem_ong:  # doacao marcada como concluida sem match concluido: nao ha ONG para localizar
        regioes["Sem ONG vinculada"]["kg"] += sem_ong

    resultado = []
    for regiao, dados in regioes.items():
        posicoes = []
        for ong_id in dados["ongs"]:
            ong = ong_por_id.get(ong_id)
            latitude, longitude = coordenadas.get(ong_id, (None, None))
            posicao, origem = geo.resolver_posicao(latitude, longitude, ong[4] if ong else None)
            if posicao:
                posicoes.append((posicao, origem))
        ponto = None
        if posicoes:
            ponto = {
                "latitude": round(sum(p[0][0] for p in posicoes) / len(posicoes), 4),
                "longitude": round(sum(p[0][1] for p in posicoes) / len(posicoes), 4),
                "posicao_origem": geo.ORIGEM_COORDENADAS if all(p[1] == geo.ORIGEM_COORDENADAS for p in posicoes) else geo.ORIGEM_CIDADE,
            }
        resultado.append({
            "regiao": regiao, "kg_entregues": round(dados["kg"], 2), "refeicoes": round(dados["kg"] / KG_POR_REFEICAO),
            "ongs": len(dados["ongs"]), **(ponto or {"latitude": None, "longitude": None, "posicao_origem": None}),
        })
    return sorted(resultado, key=lambda r: (-r["kg_entregues"], r["regiao"]))


def seguranca():
    return json.loads(SEGURANCA_PATH.read_text(encoding="utf-8"))


def calcular(hoje=None):
    hoje = hoje or date.today()
    doacoes = listar_doacoes()
    regioes_doador = {linha[0]: (linha[4] or "Sem região") for linha in listar_doadores()}
    ongs = listar_ongs()
    matches = listar_matches()
    inicio_da_oferta = inicio_por_doacao()  # quando o doador enviou a oferta (a doacao so nasce na aprovacao)
    confirmacoes = listar_confirmacoes()
    coordenadas_ongs = listar_coordenadas()

    por_regiao = defaultdict(lambda: {status: 0.0 for status in STATUS_DOACAO})
    cadastro_por_doacao = {}
    criticos = {"lotes": 0, "kg": 0.0}
    kg_concluidas = {}
    for id_, doador_id, _nome, _alimento, _cat, quantidade, validade, status, cadastro in doacoes:
        kg = float(quantidade)
        regiao = regioes_doador.get(doador_id, "Sem região")
        if status in por_regiao[regiao]:
            por_regiao[regiao][status] += kg
        cadastro_por_doacao[id_] = _mais_cedo(cadastro, inicio_da_oferta.get(id_))
        if status == "concluida":
            kg_concluidas[id_] = kg
        if status == "disponivel" and validade is not None and (_data(validade) - hoje).days <= DIAS_VALIDADE_CRITICA:
            criticos["lotes"] += 1
            criticos["kg"] += kg

    regioes = []
    for regiao, kgs in sorted(por_regiao.items()):
        regioes.append({
            "regiao": regiao,
            "kg_salvos": round(kgs["concluida"], 2),
            "refeicoes": round(kgs["concluida"] / KG_POR_REFEICAO),
            "kg_por_status": {k: round(v, 2) for k, v in kgs.items()},
        })
    kg_salvos = sum(r["kg_salvos"] for r in regioes)
    atendidas = _atendimento_por_regiao(kg_concluidas, matches, ongs, coordenadas_ongs)

    horas = []
    por_status = defaultdict(int)
    entregas = {"concluidas": 0, "confirmadas_pela_ong": 0, "confirmadas_pelo_gestor": 0}
    for id_match, doacao_id, _alimento, _ong_id, _ong, _score, _prio, status, data_match in matches:
        por_status[status] += 1
        if status == "concluido":
            entregas["concluidas"] += 1
            origem = confirmacoes.get(id_match)
            if origem == "ong":
                entregas["confirmadas_pela_ong"] += 1
            elif origem == "gestor":
                entregas["confirmadas_pelo_gestor"] += 1
        inicio, fim = _como_datetime(cadastro_por_doacao.get(doacao_id)), _como_datetime(data_match)
        if inicio and fim and fim >= inicio:
            horas.append((fim - inicio).total_seconds() / 3600)

    m = inferencia.metricas()
    return {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "impacto": {
            "kg_salvos": round(kg_salvos, 2),
            "refeicoes_estimadas": round(kg_salvos / KG_POR_REFEICAO),
            "kg_por_refeicao": KG_POR_REFEICAO,
            "kg_disponiveis": round(sum(r["kg_por_status"]["disponivel"] for r in regioes), 2),
            "doacoes": len(doacoes),
            "ongs": len(ongs),
            "lotes_validade_critica": {"dias": DIAS_VALIDADE_CRITICA, "lotes": criticos["lotes"], "kg": round(criticos["kg"], 2)},
            "por_regiao": regioes,
            "por_regiao_atendida": atendidas,
            "nota": "Kg salvos = doações concluídas (a ONG confirma o recebimento no portal, ou o gestor conclui). "
                    "Refeições = kg ÷ fator estimado. O mapa mostra onde o alimento chegou: a região da ONG que recebeu.",
        },
        "matches": {
            "total": len(matches),
            "por_status": dict(por_status),
            "tempo_medio_horas": round(sum(horas) / len(horas), 2) if horas else None,
            "amostra_tempo": len(horas),
            "entregas": entregas,
            "nota": "Tempo entre o envio da oferta (ou o cadastro da doação pelo gestor) e a criação do match.",
        },
        "ia": {
            "acuracia": m["teste"]["acuracia"],
            "acuracia_baseline": m["teste"]["acuracia_baseline"],
            "f1_macro": m["teste"]["f1_macro"],
            "recall_alto_risco": m["teste"]["recall_alto_risco"],
            "latencia_ms": m["teste"]["latencia_media_ms_por_lote"],
            "modelo": m["modelo_escolhido"],
            "amostras_teste": m["dataset"]["teste"],
            "origem_dados": m["dataset"]["origem"],
            "limitacoes": m["limitacoes"],
        },
        "seguranca": seguranca(),
    }
