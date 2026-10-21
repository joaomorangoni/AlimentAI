"""Roda as ferramentas de seguranca e grava rede-alimenta-back/ia/seguranca.json (o dashboard le esse arquivo).

Uso, na raiz do repositorio (precisa de bandit e pip-audit no Python e de Docker para Gitleaks e Trivy):

    python ferramentas/gerar_seguranca.py

O que nao puder ser executado fica como "não executado", nunca como "sem achados". Este e um retrato local: a execucao
oficial e a do GitHub Actions. O bloco "vulnerabilidades" (o que foi corrigido ao longo do projeto) e mantido do arquivo
anterior, porque vem de comparacoes entre execucoes e nao de uma unica rodada."""
import json
import re
import subprocess  # nosec B404 - so executa as ferramentas abaixo, com argumentos fixos
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "rede-alimenta-back" / "ia" / "seguranca.json"
GITLEAKS = "ghcr.io/gitleaks/gitleaks:v8.30.0"
TRIVY = "aquasec/trivy:latest"
IMAGEM = "alimenta:seguranca"
NAO = "não executado"


def rodar(comando, cwd=RAIZ, tempo=900):
    try:
        return subprocess.run(comando, cwd=cwd, capture_output=True, text=True, timeout=tempo, check=False)  # nosec B603
    except (OSError, subprocess.TimeoutExpired):
        return None


def docker_ok():
    resultado = rodar(["docker", "info"], tempo=30)
    return bool(resultado and resultado.returncode == 0)


def bandit():
    r = rodar([sys.executable, "-m", "bandit", "-r", "rede-alimenta-back", "ml", "-x",
               "rede-alimenta-back/tests,rede-alimenta-back/vendor", "-f", "json", "-q"])
    if not r or not r.stdout.strip().startswith("{"):
        return NAO, None
    achados = json.loads(r.stdout)["results"]
    bloqueiam = [a for a in achados if a["issue_severity"] in ("MEDIUM", "HIGH") and a["issue_confidence"] in ("MEDIUM", "HIGH")]
    versao = (rodar([sys.executable, "-m", "bandit", "--version"]) or r).stdout.split()
    texto = "sem achados" if not achados else f"{len(achados)} achado(s), {len(bloqueiam)} bloqueiam"
    return texto, "bandit " + (versao[1] if len(versao) > 1 else "?")


def pip_audit():
    total, versao = 0, None
    for arquivo in ("rede-alimenta-back/requirements.txt", "ml/requirements-ml.txt"):
        r = rodar([sys.executable, "-m", "pip_audit", "-r", arquivo, "-f", "json"])
        if not r or not r.stdout.strip().startswith("{"):
            return NAO, None
        total += sum(len(d.get("vulns", [])) for d in json.loads(r.stdout)["dependencies"])
    v = rodar([sys.executable, "-m", "pip_audit", "--version"])
    versao = "pip-audit " + v.stdout.split()[-1] if v and v.stdout.split() else None
    return ("sem achados" if total == 0 else f"{total} vulnerabilidade(s)"), versao


def gitleaks(com_docker):
    if not com_docker:
        return NAO
    r = rodar(["docker", "run", "--rm", "-v", f"{RAIZ}:/repo", GITLEAKS, "detect", "--source", "/repo", "--no-banner"])
    if not r or r.returncode not in (0, 1):
        return NAO
    commits = re.search(r"(\d+) commits scanned", r.stdout + r.stderr)
    base = f"histórico de {commits.group(1)} commits" if commits else "histórico"
    return ("sem achados" if r.returncode == 0 else "vazamento encontrado") + f" ({base})"


def trivy(com_docker):
    if not com_docker:
        return NAO, NAO
    montagem = ["-v", "/var/run/docker.sock:/var/run/docker.sock"]
    config = rodar(["docker", "run", "--rm", "-v", f"{RAIZ}:/repo", TRIVY, "config", "-q", "--severity", "HIGH,CRITICAL",
                    "--exit-code", "1", "/repo"])
    construcao = rodar(["docker", "build", "-q", "-t", IMAGEM, "."])
    imagem = None
    if construcao and construcao.returncode == 0:
        imagem = rodar(["docker", "run", "--rm", *montagem, TRIVY, "image", "-q", "--severity", "HIGH,CRITICAL",
                        "--scanners", "vuln,secret,misconfig", "--exit-code", "1", IMAGEM])
    resultado = lambda r: NAO if r is None else ("sem achados" if r.returncode == 0 else "achados HIGH/CRITICAL")  # noqa: E731
    return resultado(imagem), resultado(config)


def versao_trivy(com_docker):
    if not com_docker:
        return None
    r = rodar(["docker", "run", "--rm", TRIVY, "--version"], tempo=120)
    achou = re.search(r"Version:\s*(\S+)", r.stdout) if r else None
    return f"trivy {achou.group(1)}" if achou else None


def testes():
    r = rodar([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=RAIZ / "rede-alimenta-back")
    if not r:
        return NAO
    if "ModuleNotFoundError" in r.stderr:
        return NAO + " (faltam as dependências do backend neste Python)"
    quantos = re.search(r"Ran (\d+) tests", r.stderr)
    return f"{quantos.group(1)} aprovados" if r.returncode == 0 and quantos else "falharam"


def commit_base():
    r = rodar(["git", "rev-parse", "--short", "HEAD"], tempo=30)
    sujo = rodar(["git", "status", "--porcelain"], tempo=30)
    base = r.stdout.strip() if r and r.returncode == 0 else "desconhecido"
    return base + (" + alterações locais" if sujo and sujo.stdout.strip() else "")


def main():
    anterior = json.loads(SAIDA.read_text(encoding="utf-8"))
    com_docker = docker_ok()
    texto_bandit, versao_bandit = bandit()
    texto_audit, versao_audit = pip_audit()
    trivy_imagem, trivy_config = trivy(com_docker)
    gates = [
        {"nome": "Bandit (backend e ml/)", "tipo": "SAST", "bloqueia": "média/alta", "ultima_execucao_local": texto_bandit},
        {"nome": "pip-audit (backend e ml/)", "tipo": "Dependências", "bloqueia": "qualquer CVE conhecida", "ultima_execucao_local": texto_audit},
        {"nome": "Gitleaks (histórico completo)", "tipo": "Segredos", "bloqueia": "qualquer vazamento", "ultima_execucao_local": gitleaks(com_docker)},
        {"nome": "Trivy imagem (vuln, secret, misconfig)", "tipo": "Container", "bloqueia": "HIGH/CRITICAL", "ultima_execucao_local": trivy_imagem},
        {"nome": "Trivy config (Dockerfile/Compose)", "tipo": "IaC", "bloqueia": "HIGH/CRITICAL", "ultima_execucao_local": trivy_config},
        {"nome": "Testes automatizados da API", "tipo": "Testes", "bloqueia": "qualquer falha", "ultima_execucao_local": testes()},
    ]
    hoje = date.today()
    anterior.update({
        "atualizado_em": hoje.isoformat(),
        "fonte": "ferramentas/gerar_seguranca.py (resultado real das ferramentas) e documentacao/05-devsecops-e-deploy.md",
        "base": commit_base(),
        "ferramentas": [v for v in (versao_bandit, versao_audit, "gitleaks v8.30.0" if com_docker else None, versao_trivy(com_docker)) if v],
        "gates": gates,
        "observacao": f"Retrato local de {hoje.strftime('%d/%m/%Y')} (base {commit_base()}); a execução oficial é a do GitHub Actions. "
                      "'Sem achados' não equivale à ausência total de vulnerabilidades.",
    })
    SAIDA.write_text(json.dumps(anterior, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for g in gates:
        print(f"{g['nome']}: {g['ultima_execucao_local']}")


if __name__ == "__main__":
    main()
