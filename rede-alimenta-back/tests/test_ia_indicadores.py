"""Testes de IA, recomendacao e indicadores com dados simulados em memoria (sem banco)."""
import json
import os
import sys
import threading
import unittest
import http.client
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TOKEN = "k" * 40
os.environ["API_TOKEN"] = TOKEN

import security  # noqa: E402
import server  # noqa: E402
from ia import inferencia  # noqa: E402
from services import geo, ia_service, indicadores_service  # noqa: E402

HOJE = date(2026, 10, 14)
LOTE = {"alimento_descricao": "pao frances", "categoria": "padaria", "quantidade_kg": 20,
        "dias_ate_validade": 1, "distancia_km": 4, "capacidade_disponivel_kg": 50}


class InferenciaTests(unittest.TestCase):
    def test_probabilidades_somam_um(self):
        r = inferencia.prever(LOTE)
        self.assertAlmostEqual(sum(r["probabilidades"].values()), 1, places=2)
        self.assertIn(r["risco_descarte"], ("baixo", "medio", "alto"))

    def test_urgente_perecivel_tem_risco_maior_que_nao_perecivel_longo(self):
        urgente = inferencia.prever(LOTE)["probabilidades"]["alto"]
        calmo = inferencia.prever({**LOTE, "alimento_descricao": "arroz 5kg", "categoria": "nao_perecivel",
                                   "dias_ate_validade": 120})["probabilidades"]["alto"]
        self.assertGreater(urgente, calmo)

    def test_valores_fora_da_faixa_do_treino_nao_extrapolam_o_modelo(self):
        faixa = inferencia.faixa_treino()
        self.assertEqual(set(faixa), {"quantidade_kg", "dias_ate_validade", "distancia_km", "capacidade_disponivel_kg"})
        normal = inferencia.prever({**LOTE, "distancia_km": 25, "capacidade_disponivel_kg": 199})
        self.assertEqual(normal["entradas_ajustadas"], [])
        enorme = inferencia.prever({**LOTE, "distancia_km": 900, "capacidade_disponivel_kg": 90000, "quantidade_kg": 5000})
        self.assertEqual(set(enorme["entradas_ajustadas"]), {"distancia_km", "capacidade_disponivel_kg", "quantidade_kg"})
        # Capacidade e distancia gigantes valem o mesmo que o limite da faixa (antes o modelo extrapolava sem freio).
        no_limite = inferencia.prever({**LOTE, "distancia_km": faixa["distancia_km"][1],
                                       "capacidade_disponivel_kg": faixa["capacidade_disponivel_kg"][1],
                                       "quantidade_kg": faixa["quantidade_kg"][1]})
        self.assertEqual(enorme["probabilidades"], no_limite["probabilidades"])

    def test_entradas_invalidas_sao_rejeitadas(self):
        ruins = [None, [], {}, {**LOTE, "quantidade_kg": -1}, {**LOTE, "quantidade_kg": float("nan")},
                 {**LOTE, "dias_ate_validade": "1"}, {**LOTE, "distancia_km": True},
                 {**LOTE, "alimento_descricao": "x" * 500}, {**LOTE, "alimento_descricao": ""},
                 {**LOTE, "categoria": 5}, {**LOTE, "capacidade_disponivel_kg": 10**9}]
        for ruim in ruins:
            with self.assertRaises(ValueError, msg=str(ruim)[:40]):
                inferencia.prever(ruim)


class RecomendacaoTests(unittest.TestCase):
    def patch(self, status="disponivel", validade=HOJE + timedelta(days=1), qtd=20, ongs=None, doador=None,
              coord_doador=(None, None), coord_ongs=None):
        doacao = (7, 1, "Pão francês", "Padaria", qtd, validade, status, datetime(2026, 10, 14, 8))
        ongs = ongs or [(1, "ONG Longe", "a@x", "1", "Zona Norte", 100), (2, "ONG Perto", "b@x", "2", "Zona Sul", 100),
                        (3, "ONG Pequena", "c@x", "3", "Zona Sul", 5)]
        return [mock.patch.object(ia_service, "buscar_doacao", return_value=doacao),
                mock.patch.object(ia_service, "buscar_doador",
                                  return_value=doador or (1, "Padaria X", "d@x", "4", "Zona Sul")),
                mock.patch.object(ia_service, "buscar_coordenadas_doador", return_value=coord_doador),
                mock.patch.object(ia_service, "listar_coordenadas_ongs", return_value=coord_ongs or {}),
                mock.patch.object(ia_service, "listar_ongs", return_value=ongs)]

    def run_reco(self, **kw):
        patches = self.patch(**kw)
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return ia_service.recomendar_ongs(7, hoje=HOJE)

    def test_filtra_capacidade_e_prioriza_mesma_regiao(self):
        r = self.run_reco()
        ids = [c["ong_id"] for c in r["recomendacoes"]]
        self.assertNotIn(3, ids)
        self.assertEqual(ids[0], 2)
        self.assertGreaterEqual(r["recomendacoes"][0]["score_ia"], r["recomendacoes"][1]["score_ia"])
        for c in r["recomendacoes"]:
            self.assertTrue(0 <= c["score_ia"] <= 1)
            self.assertNotIn("email", c)
        self.assertIn(r["prioridade_sugerida"], ("alta", "media", "baixa"))

    def test_sem_coordenadas_nem_cidade_a_distancia_e_estimada_por_regiao(self):
        r = self.run_reco()
        por_id = {c["ong_id"]: c for c in r["recomendacoes"]}
        self.assertEqual((por_id[2]["distancia_km"], por_id[2]["distancia_origem"]), (5.0, "estimativa"))
        self.assertEqual((por_id[1]["distancia_km"], por_id[1]["distancia_origem"]), (15.0, "estimativa"))

    def test_distancia_real_pelas_coordenadas_do_cadastro(self):
        # Doador em São Paulo; ONG Perto a ~9 km, ONG Longe em Campinas (~85 km, acima da faixa de treino do modelo).
        ongs = [(1, "ONG Longe", "a@x", "1", "Zona Norte", 100), (2, "ONG Perto", "b@x", "2", "Zona Sul", 100)]
        r = self.run_reco(ongs=ongs, coord_doador=(-23.55, -46.63),
                          coord_ongs={1: (-22.91, -47.06), 2: (-23.62, -46.69)})
        por_id = {c["ong_id"]: c for c in r["recomendacoes"]}
        self.assertEqual(por_id[2]["distancia_origem"], "coordenadas")
        self.assertAlmostEqual(por_id[2]["distancia_km"], 9.9, delta=1.0)
        self.assertAlmostEqual(por_id[1]["distancia_km"], 84.0, delta=4.0)
        self.assertTrue(por_id[1]["distancia_acima_da_faixa_do_modelo"])
        self.assertFalse(por_id[2]["distancia_acima_da_faixa_do_modelo"])
        self.assertEqual(r["recomendacoes"][0]["ong_id"], 2)
        self.assertIn("pelas coordenadas", por_id[2]["motivo"])
        self.assertIn("distancia_km", por_id[1]["entradas_ajustadas_ao_treino"])  # 84 km vira 25 km para o modelo
        self.assertEqual(por_id[2]["entradas_ajustadas_ao_treino"], [])

    def test_cidade_na_regiao_vale_quando_faltam_coordenadas(self):
        ongs = [(1, "ONG Campinas", "a@x", "1", "Campinas", 100), (2, "ONG Capital", "b@x", "2", "Zona Sul, São Paulo", 100)]
        r = self.run_reco(ongs=ongs, doador=(1, "Padaria X", "d@x", "4", "São Paulo"))
        por_id = {c["ong_id"]: c for c in r["recomendacoes"]}
        self.assertEqual(por_id[1]["distancia_origem"], "cidade")
        self.assertAlmostEqual(por_id[1]["distancia_km"], 84.0, delta=4.0)
        # Mesma cidade: não dá para saber a distância dentro dela, então vale a estimativa mínima de 5 km.
        self.assertEqual((por_id[2]["distancia_km"], por_id[2]["distancia_origem"]), (5.0, "cidade"))

    def test_so_doacao_disponivel(self):
        with self.assertRaises(ValueError):
            self.run_reco(status="concluida")

    def test_id_invalido(self):
        for ruim in (0, -1, "1", None):
            with self.assertRaises(ValueError):
                ia_service.recomendar_ongs(ruim)

    def test_mapeamento_de_categoria(self):
        self.assertEqual(ia_service.categoria_do_modelo("Grãos"), "nao_perecivel")
        self.assertEqual(ia_service.categoria_do_modelo("Frutas e Verduras"), "hortifruti")
        self.assertEqual(ia_service.categoria_do_modelo("Outros", "Leite integral"), "laticinios")
        self.assertEqual(ia_service.categoria_do_modelo("???"), "")


class GeoTests(unittest.TestCase):
    def test_distancia_conhecida(self):
        # São Paulo ↔ Rio de Janeiro: ~360 km em linha reta.
        sp, rio = geo.coordenadas_da_regiao("São Paulo"), geo.coordenadas_da_regiao("Rio de Janeiro")
        self.assertAlmostEqual(geo.distancia_km(sp, rio), 360, delta=15)
        self.assertEqual(geo.distancia_km(sp, sp), 0)

    def test_cidade_e_reconhecida_no_texto_da_regiao(self):
        for texto in ("Zona Sul, São Paulo", "sao paulo - SP", "Grande SÃO PAULO", "Centro de São Paulo"):
            self.assertEqual(geo.coordenadas_da_regiao(texto), geo.CIDADES["sao paulo"], texto)
        self.assertEqual(geo.coordenadas_da_regiao("São José dos Campos"), geo.CIDADES["sao jose dos campos"])
        self.assertEqual(geo.coordenadas_da_regiao("Santo André"), geo.CIDADES["santo andre"])  # não confunde com Santos
        for texto in ("Zona Sul", "", None, "Bairro Novo", "Sudeste"):
            self.assertIsNone(geo.coordenadas_da_regiao(texto), texto)

    def test_todas_as_cidades_estao_no_brasil(self):
        for nome, (lat, lon) in geo.CIDADES.items():
            self.assertTrue(-34 <= lat <= 6 and -74 <= lon <= -34, nome)

    def test_prioridade_das_fontes_de_posicao(self):
        self.assertEqual(geo.resolver_posicao(-23.0, -46.0, "Campinas"), ((-23.0, -46.0), "coordenadas"))
        self.assertEqual(geo.resolver_posicao(None, None, "Campinas"), (geo.CIDADES["campinas"], "cidade"))
        self.assertEqual(geo.resolver_posicao(None, -46.0, "Campinas")[1], "cidade")  # par incompleto não vale
        self.assertEqual(geo.resolver_posicao(999, 0, "Zona Sul"), (None, None))  # coordenada absurda é ignorada
        self.assertEqual(geo.resolver_posicao("x", "y", None), (None, None))


class IndicadoresTests(unittest.TestCase):
    def patches(self, doacoes, doadores, ongs, matches, coordenadas=None, inicio=None, confirmacoes=None):
        return [mock.patch.object(indicadores_service, "listar_doacoes", return_value=doacoes),
                mock.patch.object(indicadores_service, "listar_doadores", return_value=doadores),
                mock.patch.object(indicadores_service, "listar_ongs", return_value=ongs),
                mock.patch.object(indicadores_service, "listar_matches", return_value=matches),
                mock.patch.object(indicadores_service, "listar_coordenadas", return_value=coordenadas or {}),
                mock.patch.object(indicadores_service, "inicio_por_doacao", return_value=inicio or {}),
                mock.patch.object(indicadores_service, "listar_confirmacoes", return_value=confirmacoes or {})]

    def calcular(self, *args, **kwargs):
        patches = self.patches(*args, **kwargs)
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return indicadores_service.calcular(hoje=HOJE)

    def test_calculo(self):
        doacoes = [
            (1, 1, "Ana", "Arroz", "Grãos", 100, HOJE + timedelta(days=30), "concluida", datetime(2026, 10, 10, 8)),
            (2, 1, "Ana", "Pão", "Padaria", 10, HOJE + timedelta(days=1), "disponivel", datetime(2026, 10, 13, 8)),
            (3, 2, "Bia", "Leite", "Laticínios", 40, HOJE + timedelta(days=9), "concluida", datetime(2026, 10, 11, 8)),
            (4, 2, "Bia", "Carne", "Carnes", 5, HOJE + timedelta(days=2), "cancelada", datetime(2026, 10, 12, 8)),
        ]
        doadores = [(1, "Ana", "a@x", "1", "Zona Sul"), (2, "Bia", "b@x", "2", "Zona Norte")]
        ongs = [(1, "ONG", "o@x", "3", "Zona Leste", 500)]
        matches = [(1, 1, "Arroz", 1, "ONG", 0.9, "alta", "concluido", datetime(2026, 10, 10, 20)),
                   (2, 3, "Leite", 1, "ONG", 0.8, "media", "pendente", datetime(2026, 10, 12, 8))]
        r = self.calcular(doacoes, doadores, ongs, matches)
        self.assertEqual(r["impacto"]["kg_salvos"], 140)
        self.assertEqual(r["impacto"]["refeicoes_estimadas"], 280)
        self.assertEqual(r["impacto"]["kg_disponiveis"], 10)
        self.assertEqual(r["impacto"]["lotes_validade_critica"]["lotes"], 1)
        regioes = {x["regiao"]: x for x in r["impacto"]["por_regiao"]}
        self.assertEqual(regioes["Zona Sul"]["kg_salvos"], 100)
        self.assertEqual(regioes["Zona Norte"]["refeicoes"], 80)
        self.assertEqual(r["matches"]["total"], 2)
        self.assertEqual(r["matches"]["tempo_medio_horas"], round((12 + 24) / 2, 2))
        self.assertEqual(r["ia"]["origem_dados"], "simulado")
        self.assertEqual(r["seguranca"]["vulnerabilidades"]["criticas_altas_abertas"], 0)

    def test_atendimento_por_regiao_da_ong_e_doacao_concluida_sem_ong(self):
        # Arroz (100 kg) chegou a uma ONG de Campinas; Leite (40 kg) foi marcado como concluído sem match concluído.
        doacoes = [
            (1, 1, "Ana", "Arroz", "Grãos", 100, HOJE + timedelta(days=30), "concluida", datetime(2026, 10, 10, 8)),
            (3, 2, "Bia", "Leite", "Laticínios", 40, HOJE + timedelta(days=9), "concluida", datetime(2026, 10, 11, 8)),
        ]
        doadores = [(1, "Ana", "a@x", "1", "São Paulo"), (2, "Bia", "b@x", "2", "São Paulo")]
        ongs = [(1, "ONG Campinas", "o@x", "3", "Campinas", 500), (2, "ONG Capital", "p@x", "4", "Zona Sul", 500)]
        matches = [(1, 1, "Arroz", 1, "ONG Campinas", 0.9, "alta", "concluido", datetime(2026, 10, 10, 20)),
                   (2, 1, "Arroz", 2, "ONG Capital", 0.8, "media", "recusado", datetime(2026, 10, 10, 9))]
        r = self.calcular(doacoes, doadores, ongs, matches)
        atendidas = {x["regiao"]: x for x in r["impacto"]["por_regiao_atendida"]}
        self.assertEqual(set(atendidas), {"Campinas", "Sem ONG vinculada"})
        self.assertEqual((atendidas["Campinas"]["kg_entregues"], atendidas["Campinas"]["refeicoes"]), (100, 200))
        self.assertEqual(atendidas["Campinas"]["posicao_origem"], "cidade")  # sem coordenadas: centro da cidade
        self.assertAlmostEqual(atendidas["Campinas"]["latitude"], -22.91, places=2)
        self.assertIsNone(atendidas["Sem ONG vinculada"]["latitude"])
        self.assertEqual(sum(x["kg_entregues"] for x in atendidas.values()), r["impacto"]["kg_salvos"])
        self.assertEqual(r["impacto"]["por_regiao_atendida"][0]["regiao"], "Campinas")  # maior volume primeiro

    def test_coordenadas_da_ong_vencem_o_centro_da_cidade(self):
        doacoes = [(1, 1, "Ana", "Arroz", "Grãos", 10, HOJE + timedelta(days=30), "concluida", datetime(2026, 10, 10, 8))]
        ongs = [(1, "ONG A", "o@x", "3", "Santos", 500), (2, "ONG B", "p@x", "4", "Santos", 500)]
        matches = [(1, 1, "Arroz", 1, "ONG A", 0.9, "alta", "concluido", datetime(2026, 10, 10, 20))]
        r = self.calcular(doacoes, [(1, "Ana", "a@x", "1", "Santos")], ongs, matches,
                          coordenadas={1: (-23.90, -46.40), 2: (None, None)})
        santos = r["impacto"]["por_regiao_atendida"][0]
        self.assertEqual((santos["latitude"], santos["longitude"], santos["posicao_origem"]), (-23.9, -46.4, "coordenadas"))

    def test_tempo_do_match_conta_desde_o_envio_da_oferta(self):
        # A doação só nasce na aprovação (14h); o doador enviou a oferta às 8h: o match às 20h demorou 12 h, não 6.
        doacoes = [(1, 1, "Ana", "Arroz", "Grãos", 10, HOJE + timedelta(days=30), "reservada", datetime(2026, 10, 10, 14))]
        matches = [(1, 1, "Arroz", 1, "ONG", 0.9, "alta", "pendente", datetime(2026, 10, 10, 20))]
        r = self.calcular(doacoes, [(1, "Ana", "a@x", "1", "SP")], [(1, "ONG", "o@x", "3", "SP", 500)], matches,
                          inicio={1: datetime(2026, 10, 10, 8)})
        self.assertEqual(r["matches"]["tempo_medio_horas"], 12)
        r = self.calcular(doacoes, [(1, "Ana", "a@x", "1", "SP")], [(1, "ONG", "o@x", "3", "SP", 500)], matches)
        self.assertEqual(r["matches"]["tempo_medio_horas"], 6)

    def test_entregas_confirmadas_pela_ong(self):
        doacoes = [(i, 1, "Ana", "Arroz", "Grãos", 10, HOJE + timedelta(days=30), "concluida", datetime(2026, 10, 10, 8))
                   for i in (1, 2, 3, 4)]
        matches = [(i, i, "Arroz", 1, "ONG", 0.9, "alta", "concluido", datetime(2026, 10, 10, 20)) for i in (1, 2, 3, 4)]
        r = self.calcular(doacoes, [(1, "Ana", "a@x", "1", "SP")], [(1, "ONG", "o@x", "3", "SP", 500)], matches,
                          confirmacoes={1: "ong", 2: "ong", 3: "gestor"})
        self.assertEqual(r["matches"]["entregas"], {"concluidas": 4, "confirmadas_pela_ong": 2, "confirmadas_pelo_gestor": 1})

    def test_sem_dados(self):
        r = self.calcular([], [], [], [])
        self.assertEqual(r["impacto"]["kg_salvos"], 0)
        self.assertEqual(r["impacto"]["por_regiao_atendida"], [])



class EndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.make_server("127.0.0.1", 0)
        server.API_TOKEN = TOKEN  # cada modulo de teste usa o proprio token
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def setUp(self):
        server.REQUEST_LIMITER = security.RateLimiter(300, 60)
        server.AUTH_FAIL_LIMITER = security.RateLimiter(10, 60)

    def call(self, method, path, body=None, token=True):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + TOKEN
        conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        resp = conn.getresponse()
        data = json.loads(resp.read() or b"{}")
        conn.close()
        return resp.status, data

    def test_risco_exige_token(self):
        self.assertEqual(self.call("POST", "/api/ia/risco", LOTE, token=False)[0], 401)
        self.assertEqual(self.call("GET", "/api/indicadores", token=False)[0], 401)
        self.assertEqual(self.call("GET", "/api/doacoes/1/recomendacoes", token=False)[0], 401)

    def test_risco_ok_e_validacao(self):
        status, data = self.call("POST", "/api/ia/risco", LOTE)
        self.assertEqual(status, 200)
        self.assertIn("risco_descarte", data)
        status, data = self.call("POST", "/api/ia/risco", {**LOTE, "quantidade_kg": -5})
        self.assertEqual(status, 400)
        self.assertIn("error", data)

    def test_recomendacao_id_invalido(self):
        self.assertEqual(self.call("GET", "/api/doacoes/0/recomendacoes")[0], 400)
        self.assertEqual(self.call("GET", "/api/doacoes/abc/recomendacoes")[0], 400)


if __name__ == "__main__":
    unittest.main()
