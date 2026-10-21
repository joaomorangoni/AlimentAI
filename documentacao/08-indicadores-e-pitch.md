# Indicadores e pitch final

## Dashboard solicitado

O PDF pede impacto por região, saúde da segurança/pipeline, resultados da IA, gráficos dinâmicos, mapa de calor e alertas de validade. A aba **Indicadores** implementa o dashboard (`GET /api/indicadores`, gráficos em SVG, atualização a cada 15 s). Os números dependem dos dados do banco: para a apresentação, use `python demo_seed.py` em um banco local (dados fictícios, claramente marcados) ou registre ciclos reais de doação, match e entrega; "salvos" usa doações concluídas como proxy de entrega.

| Indicador | Definição e fonte | Situação |
|---|---|---|
| Kg de alimentos salvos | Soma de `quantidade_kg` das doações `concluida`; cada doação conta uma vez. A conclusão vem da **ONG**, que confirma o recebimento no portal, ou do **gestor**; o tile mostra a parcela confirmada pela ONG | Implementado; ainda sem comprovante da entrega |
| Refeições estimadas | Kg salvos ÷ 0,5 kg por refeição (suposição da equipe) | Implementado; apresentar como estimativa |
| Refeições por região atendida | Kg entregues agrupados pela **região da ONG que recebeu** (onde a carência foi atendida), não pela do doador; doação concluída sem match concluído aparece como "Sem ONG vinculada" | Implementado |
| Mapa das regiões atendidas | Contorno simplificado do Brasil com um círculo por região (tamanho e cor pelo volume entregue), na posição das coordenadas da ONG ou, na falta, do centro da cidade; quando as regiões estão todas juntas, um quadro de detalhe por latitude e longitude | Implementado; posição aproximada, sem mapa de carência (não há dado de demanda) |
| Tempo médio de match | Média entre o **envio da oferta** (ou o cadastro da doação pelo gestor) e a criação do match | Implementado; não mede o tempo da resposta da ONG |
| Entregas confirmadas pela ONG | Concluídas com origem `ong` ÷ concluídas (`match_confirmacoes`) | Implementado; entregas anteriores à migração 006 ficam sem origem |
| Acurácia e recall da IA | Métricas do conjunto de teste (`ia/metricas.json`) | Implementado; dados simulados, exibido no painel |
| Saúde do pipeline | Gates e última execução local (`ia/seguranca.json`, gerado por `ferramentas/gerar_seguranca.py` a partir das ferramentas reais) | Implementado; é um retrato local datado: a execução oficial é a do Actions |
| Vulnerabilidades mitigadas | Achados com correção comprovada por reanálise (44 ocorrências HIGH do Trivy e 2 baixos do Bandit) | Implementado; fonte em `05-devsecops-e-deploy.md` |
| Lotes com validade crítica | Doações disponíveis com validade em até 3 dias | Implementado; regra temporal, não previsão de IA |
| Oferta por região do doador | Mapa de calor região do doador × status da doação (kg) | Implementado por região textual |

Evitar contar o mesmo lote várias vezes por haver vários matches. Documentar filtros de período, status, origem e definição de região. Não rotular volume disponível como volume salvo.

## Roteiro sugerido de apresentação — 5 minutos

O tempo é uma proposta da equipe, não uma exigência informada pelo PDF.

| Tempo | Mensagem e demonstração |
|---|---|
| 0:00–0:45 | Problema social, público atendido e missão do projeto, com as fontes públicas de contexto listadas em [Dados e IA](03-dados-e-ia.md#curadoria-e-fontes-de-dados) (conferir os valores nas fontes oficiais antes de citá-los) |
| 0:45–1:45 | Jornada: doador cadastra lote, ONG recebe recomendação e confirma recebimento; distinguir fluxo implementado e proposto |
| 1:45–2:45 | Dataset, modelo, baseline, métricas reais, exemplo de previsão e limitações |
| 2:45–3:45 | Arquitetura, containers, execução do pipeline, achados e correções comprovadas |
| 3:45–4:30 | Indicadores de impacto, privacidade e funcionamento na URL pública |
| 4:30–5:00 | Resultados alcançados, pendências e próximos passos |

## Texto-base adaptável

“A Rede Alimenta IA aproxima doadores e ONGs para reduzir o desperdício de alimentos. Quem tem alimento sobrando envia uma oferta sem precisar de conta e acompanha o caminho dela por um código; o gestor aprova, uma IA recomenda a ONG mais indicada considerando risco de descarte, capacidade e distância, e a própria ONG aceita e confirma o recebimento. Tudo roda em contêiner, com pipeline de segurança e banco em nuvem. Os números do painel vêm de dados simulados de demonstração e as métricas do modelo mostram o fluxo, não eficácia real: o próximo passo é treinar com dados reais de doação e descarte e calcular rotas de coleta.”

Ajustar o texto à versão que será apresentada. Não apresentar propostas como funcionalidades já disponíveis.

## Checklist da defesa

- Integrantes/RMs preenchidos (Davi Oliveira da Silva, RM 569108; João Pedro Morangoni, RM 570073; João Vitor Xavier de Carvalho, RM 570633). Falta registrar quem responde por IA, backend e DevSecOps.
- URL pública: https://alimenta-ia.onrender.com. Abra-a ~2 minutos antes de começar (o plano gratuito suspende por inatividade). Plano B se a internet falhar: Docker local (`docker compose up`) com `demo_seed.py`, e as capturas de tela guardadas.
- Dataset e modelo disponíveis com métricas reais.
- Demonstração com dados sintéticos ou agregados apropriados.
- Docker/Compose, pipeline e relatórios rastreáveis ao commit.
- Matriz STRIDE, controles e plano de privacidade revisados.
- Indicadores com fórmulas, fontes, período e limitações.
- README e esta documentação atualizados com evidências.

## Roteiro da demonstração ao vivo (3 minutos dentro do pitch)

0. **Gestor** e **ONG** entram com **e-mail e senha** (contas individuais); o painel mostra o nome de quem entrou e a página Auditoria registra o que cada um faz.
1. **Doador** abre `/doar` e envia uma oferta (ex.: "banana", hortifrúti, 12 kg). A página mostra o **código de acompanhamento**; abrir `/acompanhar` mostra a etapa ("estamos analisando a sua oferta").
2. **Gestor** entra em `/admin`: a oferta aparece em "Ofertas aguardando aprovação" (o doador ainda não existe na rede). **Aprovar** cria o doador e a doação. Em Doações, **Recomendar ONG** mostra o ranking por IA (risco de descarte, capacidade e **distância real**, com a origem de cada número).
3. **Criar match**: a doação fica "Reservada". Em Matches, **Avisar ONG** abre o e-mail ou o WhatsApp com o link pessoal e a mensagem prontos.
4. **ONG** entra no celular com a sua conta (ou, no primeiro acesso, pelo link, que serve de convite para criar a conta), vê a doação e **aceita**: o contato do doador aparece só agora, e a página de acompanhamento do doador passa a dizer "uma ONG aceitou". Quando o alimento chega, a ONG **confirma o recebimento**.
5. Em **Indicadores**, os kg salvos e as refeições sobem na hora (atualiza a cada 15 s), com a parcela confirmada pela ONG e o ponto da região no mapa. O gestor também pode concluir pelo botão **Concluir entrega**.
6. Fechar mostrando o mapa de calor, a acurácia da IA e os Security Gates, e o pedido de acesso de uma ONG nova (`/ong`) chegando ao painel.

Ensaio sem internet: `python demo_seed.py` (banco local) imprime códigos de acompanhamento de exemplo (`/acompanhar#demo-oferta-NNN-acompanhar`) em vários estados.

## Perguntas prováveis da banca

O arquivo `documentacao/perguntas-e-respostas.pdf` reúne perguntas e respostas sobre a estrutura do projeto para ensaiar a defesa.
