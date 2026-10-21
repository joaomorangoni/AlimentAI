"""Entradas aleatorias e hostis: os services so podem recusar com ValueError (ou ValidacaoIndisponivel), nunca com erro interno."""
import os
import random
import string
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ia import validador_alimento  # noqa: E402
from services import doacao_service, doador_service, match_service, ong_service, publico_service, validacao  # noqa: E402

HOJE = validacao.hoje()
TEXTOS = ["", " ", "a", "tomate", "Pão francês", "cachorro", "x" * 300, "<script>alert(1)</script>", "'; DROP TABLE doacoes;--",
          "\x00", "ar\nroz", "​", "2026-02-30", "9999-12-31", (HOJE + timedelta(days=5)).isoformat(), "hortifruti", "padaria",
          "a@b.com", "maria@exemplo.com", "(11) 91234-5678", "São Paulo", "NaN", "Infinity", "-0", "1e999", "𝒳𝒴𝒵", "\ud800"]
NUMEROS = [0, 1, -1, 0.001, 5, 10.5, 10001, 2 ** 31, 2 ** 70, -2 ** 70, 1e308, 1e-300, float("nan"), float("inf"), -float("inf")]


def valor(rng, profundidade=0):
    tipo = rng.choice(["t", "t", "n", "n", "b", "z", "l", "o", "d"] if profundidade < 2 else ["t", "n", "b", "z"])
    if tipo == "t":
        return rng.choice(TEXTOS) if rng.random() < 0.7 else "".join(rng.choice(string.printable) for _ in range(rng.randint(0, 40)))
    if tipo == "n":
        return rng.choice(NUMEROS)
    if tipo == "b":
        return rng.choice([True, False])
    if tipo == "z":
        return None
    if tipo == "l":
        return [valor(rng, profundidade + 1) for _ in range(rng.randint(0, 3))]
    if tipo == "d":
        return HOJE + timedelta(days=rng.randint(-5, 5))
    return {str(valor(rng, profundidade + 1))[:4]: valor(rng, profundidade + 1) for _ in range(rng.randint(0, 3))}


class FuzzTest(unittest.TestCase):
    def setUp(self):
        validador_alimento._cache.clear()
        ambiente = mock.patch.dict(os.environ, {"LLM_BASE_URL": "", "LLM2_BASE_URL": "", "ALIMENTO_FALHA_ABERTA": ""})
        ambiente.start()
        self.addCleanup(ambiente.stop)
        self.rng = random.Random(int(os.getenv("FUZZ_SEED", "20261014")))

    def so_recusa_limpo(self, funcao, quantidade=400):
        for _ in range(quantidade):
            argumentos = [valor(self.rng) for _ in range(funcao.__code__.co_argcount)]
            try:
                funcao(*argumentos)
            except (ValueError, doacao_service.ValidacaoIndisponivel):
                pass
            except Exception as erro:  # noqa: BLE001
                self.fail(f"{funcao.__name__}{tuple(argumentos)!r} levantou {type(erro).__name__}: {erro}")

    def test_validadores(self):
        for funcao in (validacao.nome, validacao.regiao, validacao.email, validacao.telefone, doacao_service.validar_alimento,
                       doacao_service.validar_categoria, doacao_service.validar_quantidade):
            self.so_recusa_limpo(funcao)
        for funcao in (lambda a: validacao.inteiro_id(a, "ID"), lambda a, b: validacao.coordenadas(a, b),
                       lambda a: validacao.data_iso(a, "Data"), lambda a: validacao.numero(a, "N", 0, 1),
                       lambda a, b: doacao_service.validar_validade(a, b), lambda a, b: doacao_service.validar_com_ia(a, b)):
            self.so_recusa_limpo(funcao)

    def test_cadastros_com_repositorio_falso(self):
        with mock.patch.object(doacao_service, "buscar_doador", return_value=(1,)), \
                mock.patch.object(doacao_service, "listar_doacoes", return_value=[]), \
                mock.patch.object(doacao_service, "cadastrar_doacao", return_value=1), \
                mock.patch.object(doador_service, "cadastrar_doador", return_value=1), \
                mock.patch.object(ong_service, "cadastrar_ong", return_value=1), \
                mock.patch.object(publico_service.oferta_repository, "criar", return_value=1):
            self.so_recusa_limpo(doacao_service.criar_doacao)
            self.so_recusa_limpo(doador_service.criar_doador)
            self.so_recusa_limpo(ong_service.criar_ong)
            for _ in range(400):
                dados = {c: valor(self.rng) for c in self.rng.sample(sorted(publico_service.CAMPOS_PERMITIDOS | {"x"}), self.rng.randint(0, 11))}
                try:
                    publico_service.criar_oferta(dados)
                except (ValueError, doacao_service.ValidacaoIndisponivel):
                    pass
                except Exception as erro:  # noqa: BLE001
                    self.fail(f"criar_oferta({dados!r}) levantou {type(erro).__name__}: {erro}")

    def test_match_e_edicoes_com_repositorio_falso(self):
        doacao = (5, 1, "Tomate", "hortifruti", 10.0, HOJE + timedelta(days=3), "disponivel", None)
        with mock.patch.object(match_service, "buscar_doacao", return_value=doacao), \
                mock.patch.object(match_service, "buscar_ong", return_value=(2, "ONG", "o@o.org", None, "SP", 50.0)), \
                mock.patch.object(match_service, "listar_matches", return_value=[]), \
                mock.patch.object(match_service.fluxo_repository, "criar_match_reservando", return_value=1), \
                mock.patch.object(match_service, "buscar_match", return_value=(1, 5, 2, 0.8, "alta", "pendente", None)), \
                mock.patch.object(match_service.fluxo_repository, "mudar_status_match"), \
                mock.patch.object(doacao_service, "buscar_doacao", return_value=doacao), \
                mock.patch.object(doacao_service, "atualizar_doacao"), \
                mock.patch.object(doador_service, "buscar_doador", return_value=(1,)), \
                mock.patch.object(doador_service, "atualizar_doador"), \
                mock.patch.object(ong_service, "buscar_ong", return_value=(2,)), \
                mock.patch.object(ong_service, "atualizar_ong"):
            for funcao in (match_service.criar_match, match_service.alterar_status_match, doacao_service.editar_doacao,
                           doador_service.editar_doador, ong_service.editar_ong):
                self.so_recusa_limpo(funcao)


if __name__ == "__main__":
    unittest.main()
