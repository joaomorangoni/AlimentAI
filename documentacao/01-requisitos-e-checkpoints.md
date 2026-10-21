# Requisitos e checkpoints

## Objetivo social

Conectar excedentes de alimentos de doadores às necessidades de ONGs, reduzindo desperdício e apoiando a distribuição urbana. O valor social deve ser demonstrado por resultados verificáveis, além de cadastros e telas.

## Escopo e situação atual

| Requisito do enunciado | Situação observada | Evidência ou ação necessária |
|---|---|---|
| Gestão de doações e instituições | Implementada: painel do gestor, página pública `/doar` (a oferta fica em fila própria e só vira doador e doação na aprovação), acompanhamento da oferta pelo doador (`/acompanhar`, por código), portal da ONG por link (aceitar, recusar e confirmar o recebimento) e status sincronizados (match reserva/conclui a doação). Validação estrita de todos os cadastros | `frontend/`, `services/`, `repositories/`, `migracoes/` |
| Python 3.10+ | Código Python; versão mínima ainda precisa ser testada | Registrar versão usada na entrega |
| FastAPI e Swagger | Swagger UI local e OpenAPI implementados; a API usa `http.server` com threads (FastAPI não adotado) | `/docs` e `/openapi.json`; justificar a escolha na defesa ou migrar |
| Streamlit/Gradio | Divergência; interface atual é HTML/CSS/JS | Implementar stack prevista ou validar alternativa com professor |
| Dataset público ou simulado | Implementado (simulado, 3000 lotes, seed 42) | `ml/generate_dataset.py`, `ml/data/lotes_simulados.csv`; dicionário em `03-dados-e-ia.md` |
| Modelo local com scikit-learn/Hugging Face | Implementado (scikit-learn, regressão logística) | `ml/train.py`, `ml/predict.py`, `ml/reports/metricas.json`; Hugging Face não usado |
| Priorização e análise de tipo/validade | Implementado | Modelo classifica risco de descarte (baixo/médio/alto) usando descrição, categoria, validade, quantidade; `POST /api/ia/risco` e prioridade sugerida |
| Recomendação geográfica e rotas | **Parcial (distância real implementada; rotas não)** | Recomendação por capacidade, risco e distância em linha reta (haversine) pelas coordenadas do cadastro, pelo centro da cidade da região ou, na falta, estimada por região (a tela diz qual); mapa das regiões atendidas no dashboard. Sem rotas de coleta nem tempo de deslocamento |
| Match em tempo real | Parcial (sem push; atualização por polling) | `GET /api/doacoes/{id}/recomendacoes` e botão "Recomendar ONG" com criação do match; botão "Avisar ONG" (e-mail ou WhatsApp com o link); painel do gestor atualiza a cada 30 s, dashboard a cada 15 s, portal da ONG a cada 20 s e página de acompanhamento a cada 30 s. Não há envio automático de e-mail |
| Matriz STRIDE | Implementada e atualizada com controles e risco residual | `04-matriz-stride.md` |
| Dockerfile e Compose | Implementado e testado localmente | `Dockerfile`, `compose.yaml` |
| GitHub Actions CI/CD | Implementado; execução do novo workflow a confirmar após o push | `.github/workflows/devsecops.yml` |
| Bandit e Trivy | Implementado (também pip-audit e Gitleaks) | Relatórios nos artefatos do Actions; resultados locais em `05-devsecops-e-deploy.md` |
| Deploy Render/Hugging Face | **Publicado** em https://alimenta-ia.onrender.com (Render, deploy manual a partir do `render.yaml`) | A cada atualização: novo deploy manual (as migrações rodam sozinhas ao iniciar) |
| Banco Supabase/MongoDB Atlas | Integrado e em uso (PostgreSQL/Supabase, Session pooler); esquema base versionado em `rede-alimenta-back/database/schema.sql` + migrações 001 a 006, aplicadas ao iniciar o servidor (`AUTO_MIGRAR=1`) ou com `python migrar.py` | Conferir "Banco atualizado" no log após cada deploy |
| Autenticação e perfis | **Implementado:** contas individuais de gestor e de pessoas de ONG (senha PBKDF2, sessão de 12 h, troca da senha provisória, bloqueio por tentativas), perfis no servidor, link da ONG como convite (desativável), página Acessos e trilha de **Auditoria** | `services/autenticacao_service.py`, `migracoes/007_*`, STRIDE S01, S04, R01, E03 e I07; pendente: MFA e recuperação de senha por e-mail |
| LGPD | Aviso de privacidade público em `/privacidade` (dados, finalidade, compartilhamento, retenção, direitos e canal), ligado aos formulários; acesso à API por token; recomendações sem contatos; contato do doador só após o aceite da ONG | Pendente: identidade por usuário e procedimento formal de retenção/exclusão |
| Dashboard do enunciado | Implementado (aba Indicadores) | KPIs (kg salvos, refeições por região atendida, acurácia, tempo médio de match, vulnerabilidades mitigadas, validade crítica, entregas confirmadas pela ONG), gráficos, mapa do Brasil com detalhe ampliado, mapa de calor região × status, IA e Security Gates; usar `demo_seed.py` ou dados reais para apresentar |
| README e pitch | README completo (equipe, RMs, URL, execução, segurança, migração) e roteiro criado | Registrar os resultados reais da apresentação |

## Plano por ciclo

Os meses abaixo são ciclos do enunciado, não datas de entrega inferidas.

| Ciclo | Entregáveis do PDF | Critério de aceite proposto |
|---|---|---|
| Mês 1 — MVP de IA | Dataset, modelo local, matriz STRIDE | Dataset reproduzível, avaliação sem vazamento e predição local demonstrada |
| Mês 2 — DevSecOps | Dockerfile/Compose, GitHub Actions, relatórios Bandit/Trivy | Build reproduzível e pipeline com bloqueio definido para falhas e vulnerabilidades |
| Mês 3 — Deploy e impacto | URL pública, banco em nuvem, README e pitch | Aplicação acessível, controles de acesso, evidências de impacto e documentação final |

## Prioridade pela rubrica

| Eixo | Peso no PDF | Evidência esperada |
|---|---|---|
| Impacto social | 30% | Utilidade validada, experiência de doadores/ONGs e indicadores verificáveis |
| Qualidade da IA | 30% | Curadoria, modelo, métricas e limitações |
| DevSecOps | 20% | Pipeline, análises de segurança e containers |
| Engenharia e defesa | 20% | Código, documentação e apresentação clara |

A matriz deve ser atualizada após cada checkpoint com responsável, data e link de evidência. Funcionalidades descritas no PDF são requisitos acadêmicos; sua presença no enunciado não comprova implementação no sistema.
