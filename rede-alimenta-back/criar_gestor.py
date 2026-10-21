"""Cria uma conta de gestor direto no banco (o primeiro acesso ao painel, ou a recuperacao se todos perderem a senha).

    python criar_gestor.py "Nome Completo" email@organizacao.org

Imprime uma senha provisoria (aparece so agora); no primeiro login a pessoa define a propria senha. Usa o DATABASE_URL do
.env e aplica as migracoes antes, se faltarem. Tambem da para criar pela API, com o token: POST /api/usuarios."""
import sys

import migrar
from services import autenticacao_service


def main(argumentos):
    if len(argumentos) != 3:
        sys.exit('Uso: python criar_gestor.py "Nome Completo" email@organizacao.org')
    migrar.aplicar()
    try:
        resultado = autenticacao_service.criar_usuario("gestor", argumentos[1], argumentos[2])
    except ValueError as erro:
        sys.exit("Não foi possível criar: " + str(erro))
    print("Gestor criado.")
    print("Senha provisória (aparece só agora):", resultado["senha_provisoria"])
    print("No primeiro login, a pessoa define a própria senha.")


if __name__ == "__main__":
    main(sys.argv)
