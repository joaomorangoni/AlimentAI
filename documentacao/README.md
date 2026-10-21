# Documentação — Rede Alimenta IA

Documentação organizada conforme o projeto integrador de IA e DevSecOps da FIAP, apresentado pelo Prof. M.Sc Oerton Fernandes (2026). Referência: `FIAP_Projeto Integrador DevSecOps_Rede Alimenta IA_OFVS_010826.pdf`, 13 páginas, fornecido pelo integrante da equipe. Os requisitos foram resumidos; o documento original não foi copiado para o repositório.

Data da análise do código: 06/10/2026 (revisão final em 15/10/2026). Este material registra a implementação atual e propostas para completar o trabalho. Propostas, critérios de aceite e roteiros de teste não representam funcionalidades entregues nem testes executados.

## Conteúdo

| Documento | Conteúdo | Referência no PDF |
|---|---|---|
| [Requisitos e checkpoints](01-requisitos-e-checkpoints.md) | Escopo, cronograma, rubrica e situação das entregas | pp. 2–11 |
| [Arquitetura e API](02-arquitetura-e-api.md) | Componentes, dados, endpoints e regras atuais | pp. 4–5 |
| [Dados e inteligência artificial](03-dados-e-ia.md) | Curadoria, dataset proposto, avaliação e recomendação | pp. 4–7 |
| [Matriz STRIDE](04-matriz-stride.md) | Ameaças, riscos, controles e validação | p. 7 |
| [DevSecOps e deploy](05-devsecops-e-deploy.md) | Containerização, pipeline, segurança e publicação | pp. 3, 5, 8–9 |
| [Privacidade e dados](06-privacidade-e-dados.md) | Inventário e plano de adequação à LGPD | p. 9 |
| [Execução e validação](07-execucao-e-validacao.md) | Como iniciar, testar e registrar evidências | pp. 7–9, 12 |
| [Indicadores e pitch](08-indicadores-e-pitch.md) | KPIs, apresentação, roteiro da demonstração e checklist da defesa | pp. 9–11 |
| [Perguntas e respostas (PDF)](perguntas-e-respostas.pdf) | 54 perguntas sobre a estrutura do projeto, para ensaiar a defesa | pp. 10–12 |

## Identificação da entrega

- Equipe: **Davi Oliveira da Silva (RM 569108)**, **João Pedro Morangoni (RM 570073)** e **João Vitor Xavier de Carvalho (RM 570633)**.
- Turma e datas oficiais dos checkpoints: **a preencher**.
- Responsáveis por IA, backend e DevSecOps: **a definir pela equipe** (o enunciado pede a divisão de papéis; registre aqui antes da defesa).
- URL pública: **https://alimenta-ia.onrender.com** (Render). Repositório e pipeline: https://github.com/joaovitorxc/Alimenta-IA (aba Actions). Banco em nuvem: Supabase.

O protótipo oferece um painel HTML/CSS/JavaScript com API Python (token, limites e cabeçalhos de segurança), acesso a PostgreSQL por `psycopg`, modelo de IA de risco de descarte, recomendação de ONGs e dashboard de indicadores. O enunciado prevê FastAPI, interface Streamlit/Gradio, IA funcional, Docker, CI/CD e publicação. Essas diferenças estão registradas na matriz de requisitos para orientar as próximas entregas.
