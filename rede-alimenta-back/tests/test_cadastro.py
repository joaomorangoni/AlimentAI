"""Cadastros recusam dados que nao fazem sentido (datas, quantidades, doadores, textos, categorias). Sem banco e sem IA."""
import os
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ia import validador_alimento  # noqa: E402
from services import doacao_service, doador_service, match_service, ong_service, validacao  # noqa: E402

HOJE = validacao.hoje()


def em(dias):
    return (HOJE + timedelta(days=dias)).isoformat()


class SemIA(unittest.TestCase):
    def setUp(self):
        validador_alimento._cache.clear()
        ambiente = mock.patch.dict(os.environ, {"LLM_BASE_URL": "", "LLM2_BASE_URL": "", "ALIMENTO_FALHA_ABERTA": ""})
        ambiente.start()
        self.addCleanup(ambiente.stop)

    def recusa(self, funcao, *argumentos, **nomeados):
        with self.assertRaises(ValueError, msg=repr((argumentos, nomeados))):
            funcao(*argumentos, **nomeados)


class DoacaoTest(SemIA):
    def setUp(self):
        super().setUp()
        for nome, valor in (("buscar_doador", (1,)), ("listar_doacoes", []), ("cadastrar_doacao", 7)):
            patcher = mock.patch.object(doacao_service, nome, return_value=valor)
            setattr(self, nome, patcher.start())
            self.addCleanup(patcher.stop)

    def criar(self, doador=1, alimento="tomate", categoria="hortifruti", quantidade=5, validade=em(5)):
        return doacao_service.criar_doacao(doador, alimento, categoria, quantidade, validade)

    def test_cadastro_valido_grava_dados_limpos(self):
        self.assertEqual(self.criar(alimento="  Tomate   maduro "), 7)
        grava = self.cadastrar_doacao.call_args.args
        self.assertEqual(grava[:4], (1, "Tomate maduro", "hortifruti", 5.0))
        self.assertEqual(grava[4].isoformat(), em(5))

    def test_quantidades_estranhas(self):
        for q in (0, -1, -0.01, 0.001, 10.123, 10001, 1e9, 1e308, float("nan"), float("inf"), "5", None, True, [5], {"a": 1}):
            self.recusa(self.criar, quantidade=q)
        for q in (0.01, 2.5, 10000):
            self.criar(quantidade=q, alimento="tomate", validade=em(q == 10000 and 6 or 5))

    def test_datas_estranhas(self):
        for v in (em(-1), em(-3650), "2026-02-30", "2026-13-01", "31/12/2026", "20261231", "2026-1-5", "", " ", None, 20261231,
                  em(5) + "T00:00:00", "0001-01-01", "9999-12-31", "hoje", "2026-12-31; DROP TABLE doacoes", [em(5)]):
            self.recusa(self.criar, validade=v)
        self.criar(validade=em(0))

    def test_validade_coerente_com_a_categoria(self):
        self.criar(alimento="tomate", categoria="hortifruti", validade=em(60))
        self.recusa(self.criar, alimento="tomate", categoria="hortifruti", validade=em(61))
        self.criar(alimento="arroz", categoria="nao_perecivel", validade=em(1095))
        self.recusa(self.criar, alimento="arroz", categoria="nao_perecivel", validade=em(1096))
        self.recusa(self.criar, alimento="pão", categoria="padaria", validade=em(91))
        self.recusa(self.criar, alimento="marmita", categoria="prontos", validade=em(181))

    def test_doadores_estranhos(self):
        for d in (0, -5, "1", 1.5, True, None, 2 ** 31, [1], {"id": 1}, "1 OR 1=1"):
            self.recusa(self.criar, doador=d)
        self.buscar_doador.return_value = None
        self.recusa(self.criar, doador=999)

    def test_alimentos_estranhos(self):
        for a in ("", " ", "a", "123", "<script>alert(1)</script>", "x" * 61, "arroz\x00", "arroz​", "ar\nroz", 5, None,
                  "'; DROP TABLE doacoes;--", "arroz; rm -rf /", "-arroz", "@@@", "   ", ["arroz"], {"a": 1}, "cachorro", "Chinelo"):
            self.recusa(self.criar, alimento=a, categoria="nao_perecivel")

    def test_categorias_estranhas(self):
        for c in (None, "", " ", "abc", "Hortifruti", "hortifruti ", "HORTIFRUTI", 5, ["hortifruti"], "hortifruti'; --", "grãos"):
            self.recusa(self.criar, categoria=c)

    def test_categoria_que_nao_combina_com_o_alimento(self):
        for alimento, categoria in (("tomate", "carnes"), ("arroz", "laticinios"), ("frango", "hortifruti"), ("pão", "carnes"), ("leite", "padaria")):
            self.recusa(self.criar, alimento=alimento, categoria=categoria)

    def test_sem_confirmacao_da_ia_nao_cadastra(self):
        with self.assertRaises(doacao_service.ValidacaoIndisponivel):
            self.criar(alimento="zorblax", categoria="hortifruti")
        self.cadastrar_doacao.assert_not_called()

    def test_doacao_duplicada(self):
        self.listar_doacoes.return_value = [(1, 1, "Doador", "Tomate", "hortifruti", 5.0, em(5), "disponivel", None)]
        self.recusa(self.criar)
        self.listar_doacoes.return_value = [(1, 1, "Doador", "Tomate", "hortifruti", 5.0, em(5), "concluida", None)]
        self.criar()

    def test_edicao(self):
        atual = (3, 1, "Tomate", "hortifruti", 5.0, __import__("datetime").date.fromisoformat(em(5)), "disponivel", None)
        with mock.patch.object(doacao_service, "buscar_doacao", return_value=atual), \
                mock.patch.object(doacao_service, "atualizar_doacao") as grava:
            doacao_service.editar_doacao(3, "Tomate", "hortifruti", 6, em(5), "reservada")
            self.assertEqual(grava.call_args.args[1:4], ("Tomate", "hortifruti", 6.0))
            for status in ("", "invalido", None, 5, "Disponivel"):
                self.recusa(doacao_service.editar_doacao, 3, "Tomate", "hortifruti", 6, em(5), status)
            self.recusa(doacao_service.editar_doacao, 3, "Tomate", "hortifruti", 0, em(5), "disponivel")
            self.recusa(doacao_service.editar_doacao, 3, "Tomate", "hortifruti", 5, em(-1), "disponivel")
            self.recusa(doacao_service.editar_doacao, 3, "Tomate", "carnes", 5, em(5), "disponivel")
            self.recusa(doacao_service.editar_doacao, 3, "cachorro", "carnes", 5, em(5), "disponivel")
            self.recusa(doacao_service.editar_doacao, 0, "Tomate", "hortifruti", 5, em(5), "disponivel")
            self.recusa(doacao_service.editar_doacao, True, "Tomate", "hortifruti", 5, em(5), "disponivel")

    def test_edicao_de_item_ja_aprovado_nao_depende_da_ia(self):
        atual = (3, 1, "Zorblax", "hortifruti", 5.0, __import__("datetime").date.fromisoformat(em(5)), "disponivel", None)
        with mock.patch.object(doacao_service, "buscar_doacao", return_value=atual), \
                mock.patch.object(doacao_service, "atualizar_doacao") as grava:
            doacao_service.editar_doacao(3, "Zorblax", "hortifruti", 5, em(5), "concluida")
            grava.assert_called_once()
            with self.assertRaises(doacao_service.ValidacaoIndisponivel):
                doacao_service.editar_doacao(3, "Zorblax novo", "hortifruti", 5, em(5), "concluida")

    def test_edicao_mantem_validade_antiga_ja_vencida(self):
        vencida = __import__("datetime").date.fromisoformat(em(-3))
        atual = (3, 1, "Tomate", "hortifruti", 5.0, vencida, "disponivel", None)
        with mock.patch.object(doacao_service, "buscar_doacao", return_value=atual), \
                mock.patch.object(doacao_service, "atualizar_doacao") as grava:
            doacao_service.editar_doacao(3, "Tomate", "hortifruti", 5, em(-3), "cancelada")
            grava.assert_called_once()


class DoadorOngTest(SemIA):
    def setUp(self):
        super().setUp()
        for modulo, nome in ((doador_service, "cadastrar_doador"), (ong_service, "cadastrar_ong")):
            patcher = mock.patch.object(modulo, nome, return_value=9)
            setattr(self, nome, patcher.start())
            self.addCleanup(patcher.stop)

    def doador(self, **campos):
        base = dict(nome="Maria da Silva", email="maria@exemplo.com", telefone="(11) 91234-5678", regiao="São Paulo")
        return doador_service.criar_doador(**{**base, **campos})

    def ong(self, **campos):
        base = dict(nome="ONG Mesa Cheia", email="mesa@exemplo.org", telefone=None, regiao="Osasco", capacidade_kg=100)
        return ong_service.criar_ong(**{**base, **campos})

    def test_doador_valido_e_normalizado(self):
        self.doador(nome="  Maria   da Silva ", email="Maria@Exemplo.COM")
        args = self.cadastrar_doador.call_args.args
        self.assertEqual(args[:4], ("Maria da Silva", "maria@exemplo.com", "(11) 91234-5678", "São Paulo"))
        self.assertEqual(args[4:], (None, None))

    def test_nomes_estranhos(self):
        for n in ("", " ", "a", "123", "<b>x</b>", "x" * 121, None, 5, "Maria\nSilva", "Ma​ria", "'; DROP TABLE doadores;--", ["Maria"], "!!!", "@@"):
            self.recusa(self.doador, nome=n)
            self.recusa(self.ong, nome=n)

    def test_emails_estranhos(self):
        for e in ("", "a@b", "a@b.c", "@x.com", "a b@x.com", "a@@x.com", "a..b@x.com", ".a@x.com", "a@x", 5, None,
                  "javascript:alert(1)@x.com", "a@x.com\nbcc:b@x.com", "a" * 70 + "@x.com", "<a>@x.com", "a@-.com", "x@x..com"):
            self.recusa(self.doador, email=e)
            self.recusa(self.ong, email=e)

    def test_telefones_estranhos(self):
        for t in ("abc", "123", "00000000000", "1" * 21, "11 9999", 11999999999, ["11999999999"], "(11) 9123-45678-9", "+++", "11\n99999999"):
            self.recusa(self.doador, telefone=t)
        for t in (None, "", "  ", "(11) 91234-5678", "+55 11 91234-5678", "11912345678", "1132345678"):
            self.doador(telefone=t)

    def test_regioes_estranhas(self):
        for r in ("", "1", "<x>", "S", 5, None, "x" * 81, "São Paulo; --", "123"):
            self.recusa(self.doador, regiao=r)
        self.doador(regiao="São José dos Campos")
        self.doador(regiao="Santa Bárbara d'Oeste")

    def test_coordenadas(self):
        for lat, lon in ((1.0, None), (None, 1.0), (48.85, 2.35), (-23.5, 2.35), (100, -46), (float("nan"), -46), ("x", -46), (True, -46), (-23.5, float("inf"))):
            self.recusa(self.doador, latitude=lat, longitude=lon)
        self.doador(latitude=-23.55, longitude=-46.63)
        self.doador(latitude=None, longitude=None)

    def test_capacidades_estranhas(self):
        for c in (0, -1, 0.001, 1e9, 1000001, None, "5", True, float("nan"), float("inf"), [5]):
            self.recusa(self.ong, capacidade_kg=c)
        self.ong(capacidade_kg=0.01)
        self.ong(capacidade_kg=1000000)

    def test_edicao_valida_os_mesmos_campos(self):
        with mock.patch.object(doador_service, "buscar_doador", return_value=(1,)), \
                mock.patch.object(doador_service, "atualizar_doador") as grava:
            doador_service.editar_doador(1, "Maria Souza", "", "Santos")
            self.assertEqual(grava.call_args.args, (1, "Maria Souza", None, "Santos"))
            self.recusa(doador_service.editar_doador, 1, "", None, "Santos")
            self.recusa(doador_service.editar_doador, 1, "Maria", "abc", "Santos")
            self.recusa(doador_service.editar_doador, 0, "Maria", None, "Santos")
        with mock.patch.object(ong_service, "buscar_ong", return_value=(1,)), \
                mock.patch.object(ong_service, "atualizar_ong"):
            self.recusa(ong_service.editar_ong, 1, "ONG Boa", None, "Osasco", -5)
            self.recusa(ong_service.editar_ong, 1, "ONG Boa", None, "Osasco", "100")


class MatchTest(SemIA):
    DOACAO = (5, 1, "Tomate", "hortifruti", 10.0, __import__("datetime").date.fromisoformat(em(3)), "disponivel", None)
    ONG = (2, "ONG", "o@o.org", None, "SP", 50.0)

    def criar(self, doacao_id=5, ong_id=2, score=0.8, prioridade="alta", doacao=None, ong=None, existentes=()):
        with mock.patch.object(match_service, "buscar_doacao", return_value=doacao or self.DOACAO), \
                mock.patch.object(match_service, "buscar_ong", return_value=ong or self.ONG), \
                mock.patch.object(match_service, "listar_matches", return_value=list(existentes)), \
                mock.patch.object(match_service.fluxo_repository, "criar_match_reservando", return_value=11) as grava:
            resultado = match_service.criar_match(doacao_id, ong_id, score, prioridade)
            return resultado, grava

    def test_match_valido(self):
        self.assertEqual(self.criar()[0], 11)

    def test_ids_scores_e_prioridades_estranhos(self):
        for campos in ({"doacao_id": 0}, {"doacao_id": "5"}, {"doacao_id": True}, {"ong_id": -1}, {"ong_id": 1.5}, {"ong_id": None},
                       {"score": 1.5}, {"score": -0.1}, {"score": float("nan")}, {"score": "0.5"}, {"score": None}, {"score": 0.123456},
                       {"prioridade": "urgente"}, {"prioridade": "ALTA"}, {"prioridade": None}, {"prioridade": 1}):
            self.recusa(self.criar, **campos)

    def test_regras_de_negocio(self):
        base = list(self.DOACAO)
        for status in ("reservada", "concluida", "cancelada"):
            self.recusa(self.criar, doacao=tuple(base[:6] + [status] + base[7:]))
        vencida = __import__("datetime").date.fromisoformat(em(-1))
        self.recusa(self.criar, doacao=tuple(base[:5] + [vencida] + base[6:]))
        self.recusa(self.criar, ong=(2, "ONG", "o@o.org", None, "SP", 5.0))
        ativo = (1, 5, "Tomate", 2, "ONG", 0.5, "alta", "pendente", None)
        self.recusa(self.criar, existentes=[ativo])
        recusado = (1, 5, "Tomate", 2, "ONG", 0.5, "alta", "recusado", None)
        self.assertEqual(self.criar(existentes=[recusado])[0], 11)

    def test_inexistentes(self):
        with mock.patch.object(match_service, "buscar_doacao", return_value=None):
            self.recusa(match_service.criar_match, 5, 2, 0.5, "alta")
        with mock.patch.object(match_service, "buscar_doacao", return_value=self.DOACAO), \
                mock.patch.object(match_service, "buscar_ong", return_value=None):
            self.recusa(match_service.criar_match, 5, 2, 0.5, "alta")

    def test_status_do_match_respeita_as_transicoes(self):
        def com_status(atual):
            return (1, 5, 2, 0.8, "alta", atual, None)

        for atual, novo, valido in (("pendente", "aceito", True), ("pendente", "recusado", True), ("aceito", "concluido", True),
                                    ("aceito", "recusado", True), ("pendente", "concluido", False), ("concluido", "pendente", False),
                                    ("recusado", "aceito", False), ("concluido", "recusado", False)):
            with mock.patch.object(match_service, "buscar_match", return_value=com_status(atual)), \
                    mock.patch.object(match_service.fluxo_repository, "mudar_status_match") as grava:
                if valido:
                    match_service.alterar_status_match(1, novo)
                    grava.assert_called_once_with(1, novo, atual, "gestor" if novo == "concluido" else None)
                else:
                    self.recusa(match_service.alterar_status_match, 1, novo)
                    grava.assert_not_called()

    def test_status_do_match_invalido(self):
        with mock.patch.object(match_service, "buscar_match", return_value=(1, 5, 2, 0.8, "alta", "pendente", None)):
            for status in ("", "feito", None, 1, "ACEITO"):
                self.recusa(match_service.alterar_status_match, 1, status)


if __name__ == "__main__":
    unittest.main()
