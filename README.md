# Alimenta-IA · Rede Alimenta

Documentação do projeto integrador, requisitos, arquitetura, IA, STRIDE, DevSecOps e roteiro de defesa: [documentacao/README.md](documentacao/README.md).

**Equipe:** Davi Oliveira da Silva (RM 569108), João Pedro Morangoni (RM 570073) e João Vitor Xavier de Carvalho (RM 570633) · FIAP, Tecnólogo em Inteligência Artificial, 1º ano, Projeto Integrador (Prof. M.Sc Oerton Fernandes).

**URL pública:** https://alimenta-ia.onrender.com (Render, plano gratuito; o primeiro acesso após inatividade pode levar ~1 min para acordar o serviço). Banco em nuvem: Supabase (PostgreSQL). Pipeline: [GitHub Actions](https://github.com/joaovitorxc/Alimenta-IA/actions).

Painel responsivo em português com visão geral, busca e gerenciamento de doações, doadores, ONGs e matches, mais uma página pública de doação (com acompanhamento por código) e um portal para as ONGs (veja [Papéis e fluxo](#papéis-e-fluxo)). Frontend em HTML, CSS e JavaScript, servido na mesma origem pela API Python, que utiliza os serviços e repositórios existentes.

## Executar no Windows

Na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -m pip install -r rede-alimenta-back\requirements.txt
cd rede-alimenta-back
..\.venv\Scripts\python.exe server.py
```

Configure `DATABASE_URL` e `API_TOKEN` no arquivo `rede-alimenta-back/.env` (veja [Segurança](#segurança)). `API_TOKEN` é obrigatório: o servidor não inicia sem um token de 32+ caracteres. As tabelas são criadas sozinhas quando o servidor inicia (ou com `python migrar.py`): é aplicado o `database/schema.sql` e as migrações de `migracoes/`, todas idempotentes (veja [Migração do banco](#migração-do-banco)).

Abra **http://localhost:8000** (página inicial pública; o painel do gestor fica em **/admin**). O frontend deve ser aberto pelo servidor, não diretamente pelo arquivo HTML. Sem conexão com o banco, o painel informa o erro e permite tentar novamente.

Documentação interativa Swagger: **http://localhost:8000/docs**. Contrato OpenAPI: **http://localhost:8000/openapi.json**. Reinicie o servidor após atualizar o código. A interface Swagger é servida localmente (Swagger UI 5.33.1 vendorizado, hashes em `rede-alimenta-back/vendor/swagger-ui/SHA256SUMS`); use o botão **Authorize** com o `API_TOKEN`. O botão `Try it out` executa operações reais no banco conectado.

## Operações

- `GET /api/{doadores|ongs|doacoes|matches}`: listar.
- `POST /api/{recurso}`: cadastrar.
- `PUT /api/{recurso}/{id}`: editar campos permitidos pelos serviços.
- `DELETE /api/{recurso}/{id}`: excluir.
- `POST /api/ia/risco`: risco de descarte de um lote (modelo de IA).
- `GET /api/doacoes/{id}/recomendacoes`: ONGs sugeridas para uma doação disponível, com a distância (pelas coordenadas, pelo centro da cidade ou estimada por região).
- `GET /api/indicadores`: dados do dashboard (aba **Indicadores** do painel).
- `GET /api/ofertas` e `POST /api/ofertas/{id}/aprovar` ou `recusar`: fila das ofertas enviadas pela página pública.
- `GET /api/ong-solicitacoes` e `POST /api/ong-solicitacoes/{id}/atender` ou `descartar`: pedidos de acesso de ONGs.
- Sem token: `POST /api/publico/doacoes` (oferta), `POST /api/publico/acompanhar` (situação da oferta pelo código) e `POST /api/publico/ong-acesso` (pedido de acesso de ONG).
- Portal da ONG (link com código): `GET /api/ong-portal/matches` e `POST /api/ong-portal/matches/{id}/aceitar`, `recusar` ou `receber` (confirma o recebimento).

E-mail e coordenadas são definidos no cadastro; o backend existente não oferece edição desses campos. Em matches, a edição altera apenas o status. O score pode ser informado manualmente ou vir da recomendação por IA (botão **Recomendar ONG** em Doações).

Por padrão, o servidor escuta em localhost. `HOST` e `PORT` permitem configurar a execução em container. Para publicar atrás de proxy confiável (Render, Hugging Face), defina `TRUST_PROXY=1`.

## Deploy no Render

O arquivo `render.yaml` descreve um Web Service Docker gratuito. No Render: **New → Blueprint**, aponte para este repositório e informe `DATABASE_URL` (Session pooler do Supabase, com `?sslmode=require`) e um `API_TOKEN` novo. O `autoDeploy` está desligado: publique depois que o pipeline estiver verde. Após o deploy, abra a URL e entre em `/admin` com a senha. **Depois de cada atualização do código, faça um novo deploy manual**: ao iniciar, o servidor aplica as migrações no banco da nuvem (aditivas e idempotentes; veja o log do Render para confirmar "Banco atualizado"). URL atual: https://alimenta-ia.onrender.com.

## Executar com Docker

Com Docker Desktop iniciado, execute na raiz:

```powershell
if (-not (Test-Path rede-alimenta-back/.env)) {
    Copy-Item rede-alimenta-back/.env.example rede-alimenta-back/.env
}
```

Edite `rede-alimenta-back/.env` com sua `DATABASE_URL` real e um `API_TOKEN` novo (`python -c "import secrets; print(secrets.token_urlsafe(32))"`). As tabelas são criadas ao iniciar (ou com `python migrar.py`); o Compose não provisiona o banco, só a aplicação.

```powershell
docker compose up --build -d
docker compose ps
docker compose logs -f app
```

Abra http://localhost:8000 (painel do gestor em /admin). Para encerrar: `docker compose down`.
`GET /health` verifica apenas se o servidor responde; não comprova conexão com o banco.
A imagem usa Python 3.12 sobre Alpine 3.24 e executa a aplicação com usuário sem privilégios administrativos.

## Papéis e fluxo

| Papel | Como entra | O que faz |
|---|---|---|
| **Gestor (admin)** | Painel em `/admin`, com **e-mail e senha de conta individual** (sessão de 12 h). Não há senha única de painel. O primeiro gestor se cria com `python criar_gestor.py "Nome" email@x.org` (ou pela API com o `API_TOKEN`: `POST /api/usuarios`), e os demais em **Acessos** | Aprova ofertas, recomenda ONGs (IA), cria matches, conclui entregas, vê os indicadores, gera, desativa e vê a idade do link de cada ONG, **cria e gerencia os acessos** (Acessos) e vê **quem fez o quê** (Auditoria) |
| **Doador (qualquer pessoa)** | Página pública `/doar`, sem login | Envia uma oferta e recebe um **código de acompanhamento**; com ele, em `/acompanhar`, vê em que etapa está (analisando, aprovada, ONG indicada, ONG aceitou, entregue). Não vê nenhum dado do sistema |
| **ONG** | **Conta individual** (e-mail e senha, em `/ong`) ou, no primeiro acesso, o link pessoal `/ong#<id>.<código>` gerado pelo gestor, que funciona como convite: com ele a pessoa **cria a própria conta** e depois entra sem o link. O gestor pode desativar o link quando as contas existirem | Vê só as doações indicadas para ela, aceita ou recusa e, quando o alimento chega, **confirma o recebimento**; o sistema registra quem fez cada coisa. O contato do doador só aparece depois do aceite. Sem link, pede acesso em `/ong` (formulário público); o pedido (com CNPJ e capacidade opcionais; o CNPJ é guardado no cadastro da ONG, único quando informado) chega ao painel; o gestor confere, cadastra a ONG com os dados já preenchidos e envia o link |

Fluxo completo:

1. O doador envia a oferta em `/doar` (validada no servidor; alimento e categoria conferidos pela IA). Ela fica na fila `ofertas_publicas`, **sem criar doador nem doação**, e o doador recebe o código de acompanhamento.
2. O gestor vê a fila "Ofertas aguardando aprovação" e **aprova** (cria o doador, ou reaproveita o do mesmo e-mail, e a doação *Disponível*, numa única transação) ou **recusa** (os dados pessoais da oferta são apagados na hora). Ofertas pendentes não entram em recomendações, matches nem indicadores, e visitantes nunca aprovados não viram "doadores".
3. O gestor usa **Recomendar ONG** (IA: risco de descarte, capacidade e distância) e cria o **match**. A doação passa sozinha a **Reservada**. O botão **Avisar ONG** abre o e-mail ou o WhatsApp já com a mensagem e o link.
4. A ONG abre o link dela e **aceita** ou **recusa**. Recusar libera a doação (volta a *Disponível*).
5. Quando o alimento chega, a **ONG confirma o recebimento** no portal (ou o gestor clica em **Concluir entrega**): o match vira **Concluído**, a doação vira **Concluída** e os kg entram nos Indicadores, com o registro de quem confirmou.

O gestor também pode cadastrar doações direto no painel (já nascem *Disponíveis*). O painel se atualiza sozinho a cada 30 s, e a página de acompanhamento e o portal da ONG também. O link da ONG não tem senha: quem tiver o link tem o acesso; o gestor vê **de quando é o link** (com aviso depois de 90 dias), pode **desativá-lo** (a ONG entra só por conta) e pode **gerar um novo** a qualquer momento, e o antigo deixa de funcionar.

### Migração do banco

`python migrar.py` aplica, em ordem, o esquema base `database/schema.sql` (doadores, ONGs, doações e matches, conferido contra o Supabase) e as migrações aditivas e idempotentes de `migracoes/`, que nunca apagam nem alteram dados existentes:

- `001`: `ong_links_acesso` (versão vigente do link de cada ONG; o código é calculado no servidor).
- `002` e `003`: `ong_solicitacoes_acesso` (pedidos de acesso de ONGs, com CNPJ e capacidade opcionais).
- `004`: coluna `cnpj` opcional e única em `ongs`.
- `005`: `ofertas_publicas` (ofertas da página pública até a decisão do gestor; o código de acompanhamento é guardado só como hash).
- `006`: `match_confirmacoes` (quem confirmou cada entrega: a ONG ou o gestor).
- `007`: `usuarios` (contas de gestor e de pessoas de ONG; só o hash da senha), `usuario_sessoes` (só o hash do token), `auditoria_acoes` e a coluna `ativo` em `ong_links_acesso`. Os nomes não colidem com as tabelas de contas que o banco da equipe já tem (`ong_contas`, `doador_contas`…), que este código não usa.

**Ao iniciar, o servidor aplica tudo isso sozinho** (`AUTO_MIGRAR=1`, o padrão), então depois de cada deploy não é preciso lembrar do `migrar.py`; se o banco estiver fora do ar ou sem permissão para criar tabelas, o servidor sobe mesmo assim e registra o erro no log. Para rodar à mão, ou com `AUTO_MIGRAR=0`:

```powershell
cd rede-alimenta-back
..\.venv\Scripts\python.exe migrar.py
```

Sem a migração, o sistema continua funcionando: a oferta pública cai no fluxo antigo (cria o doador e uma doação pendente, sem código de acompanhamento), a conclusão de entregas segue valendo sem o registro de quem confirmou, o portal da ONG usa a versão inicial do link e os pedidos de acesso de ONGs avisam que estão indisponíveis. Defina `ONG_LINK_SECRET` (32+ caracteres) em produção; se ficar vazio, o segredo é derivado do `API_TOKEN`.

### Dados de demonstração

Para apresentar o dashboard com números (kg salvos, refeições por região atendida, mapa, tempo médio de match, entregas confirmadas), use `python demo_seed.py` (em `rede-alimenta-back/`). Ele cria doadores, ONGs, doações, matches, ofertas públicas e confirmações fictícios, todos com e-mail `@demo.alimenta.example` (e códigos de acompanhamento `demo-oferta-NNN-acompanhar`, que ele imprime), e `python demo_seed.py --limpar` remove só o que ele criou. O script **recusa rodar em banco que não seja local**, a menos que se passe `--confirmo-nuvem`. Não use dados de demonstração junto de dados reais sem limpar depois.

## Validação dos cadastros

Dados que não fazem sentido são recusados no servidor (HTTP 400, com mensagem clara), mesmo que o formulário seja contornado:

- **Doações:** quantidade de 0,01 a 10.000 kg (até 2 casas decimais); validade em AAAA-MM-DD, existente no calendário, não vencida e coerente com a categoria (hortifrúti até 60 dias, padaria 90, prontos 180, laticínios e carnes 365, não perecível 1.095); doador existente; categoria da lista fixa; sem doação idêntica duplicada.
- **Doadores e ONGs:** nome, e-mail (normalizado em minúsculas), telefone brasileiro (DDD + número), região, coordenadas em par e dentro do Brasil, capacidade de 0,01 a 1.000.000 kg. Textos sem caracteres de controle ou invisíveis.
- **Matches:** doação disponível e não vencida, ONG com capacidade para o volume, sem match ativo repetido, score entre 0 e 1.
- JSON com `NaN`/`Infinity`, tipos trocados (texto no lugar de número, booleano como id) e ids fora do intervalo são rejeitados.

### Validação do alimento e da categoria (IA)

Alimento errado ou na categoria errada não é cadastrado. A validação nega por padrão e tem camadas, da mais barata à mais cara:

1. **Bloqueio local:** animais, objetos, produtos de limpeza, drogas e similares são recusados sem consultar nenhuma IA (a IA não consegue sobrepor essa regra).
2. **Lista local de alimentos conhecidos:** aprova na hora, ignorando acento, plural e quantidade ("Pães", "Arroz 5kg"), e confere a categoria (itens de categoria ambígua, como biscoito, aceitam as alternativas).
3. **IA gratuita para o restante:** Groq (`openai/gpt-oss-120b`) como principal e Gemini como reserva automática. Se um provedor falhar (cota ou queda), o outro assume; um provedor com falha entra em pausa por 30 s.
4. **Falha segura:** se nada conseguir confirmar que o item é comida, o cadastro é recusado (HTTP 503, "tente novamente"). `ALIMENTO_FALHA_ABERTA=1` inverte isso, apenas para desenvolvimento.

Só o nome do alimento é enviado à IA (como dado JSON, com instrução para ignorar comandos no texto), nunca dados de doadores ou ONGs, e há limite de 30 consultas por minuto. Configure `LLM_*` e `LLM2_*` conforme `rede-alimenta-back/.env.example`; as chaves ficam no `.env` e nos secrets do Render, nunca no Git.

## Segurança

- **Autenticação:** contas individuais de **gestor** e de **pessoa de ONG** (e-mail e senha); **não existe senha única de painel**. Senhas com PBKDF2-HMAC-SHA256 (600 mil iterações, sal por senha), política (10 a 128 caracteres, sem ser só números, comum, nem conter o e-mail ou o começo do nome), troca obrigatória da senha provisória, e sessões de 12 h guardadas só como hash (desativar a conta ou trocar a senha derruba as sessões na hora). O login tem erro e tempo iguais para e-mail inexistente, senha errada e conta desativada; 5 falhas por e-mail em 15 min e 10 falhas por IP por minuto bloqueiam (inclusive para e-mails que não existem, para não revelar quem tem conta). **Perfis:** conta de ONG nunca acessa as rotas do gestor (403) e o portal usa a ONG da conta, nunca um id enviado pelo navegador. O `API_TOKEN` só vale para Swagger e scripts (aparece na auditoria como "Token da API") e é o caminho de recuperação se todos perderem a senha. O doador acompanha a oferta por um código aleatório de 128 bits (só o hash fica no banco). O link da ONG (HMAC) vira convite e pode ser desativado.
- **Auditoria:** cada ação que altera dados e deu certo, e cada login (bom ou ruim), grava quem fez, o que e quando (sem corpo de requisição, sem senhas e sem o e-mail digitado); o gestor consulta em **Auditoria**.
- **Disponibilidade:** servidor com threads, timeout de 10 s por conexão, máximo de 64 conexões, 300 requisições/min por IP e 10 falhas de autenticação/min por IP (HTTP 429).
- **Cabeçalhos:** CSP restritiva (sem scripts ou estilos inline no painel), `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Cache-Control: no-store`; HSTS atrás de proxy HTTPS.
- **Privacidade (LGPD):** aviso em [/privacidade](https://alimenta-ia.onrender.com/privacidade), com a lista de dados, finalidades, compartilhamento, retenção e canal para solicitações; ligado a todos os formulários públicos. Plano completo em [Privacidade e dados](documentacao/06-privacidade-e-dados.md).
- **Testes:** `cd rede-alimenta-back && python -m unittest discover -s tests -v` (não acessam o banco; incluem um teste que impede estilo ou script inline no frontend, que a CSP bloquearia, e outro que garante que as migrações são só aditivas e idempotentes).
- **Limites conhecidos:** não há recuperação de senha por e-mail nem verificação em duas etapas (o gestor redefine e entrega uma senha provisória); o bloqueio por tentativas e os limites de taxa ficam em memória por instância; o token da API não tem identidade individual; o doador não tem conta (só acompanha pelo código). Detalhes e risco residual em [STRIDE](documentacao/04-matriz-stride.md).

## IA (pasta `ml/`)

Dataset simulado, treino e inferência local em [documentacao/03-dados-e-ia.md](documentacao/03-dados-e-ia.md). Dependências fixadas em `ml/requirements-ml.txt`.

Na recomendação de ONGs, a distância vem das coordenadas do cadastro (linha reta, haversine), do centro da cidade citada na região (tabela de ~100 cidades) ou, na falta, de uma estimativa por região; a tela diz de onde veio cada número. O modelo só viu distâncias de até 25 km e capacidades de até ~200 kg: valores acima disso são levados ao limite da faixa (a resposta lista o que foi ajustado), para a regressão logística não extrapolar.

## Pipeline DevSecOps

O workflow `.github/workflows/devsecops.yml` executa em pull requests, pushes na `main` e manualmente pela aba **Actions** do GitHub. Valida sintaxe, executa os testes de segurança, Bandit (backend e `ml/`), pip-audit, Gitleaks (todo o histórico) e Trivy (vulnerabilidades, segredos e misconfiguração da imagem e do Dockerfile/Compose); constrói a imagem e verifica inicialização, frontend, OpenAPI, resposta 401 sem token e CSP. Não testa operações no banco. As Actions estão fixadas por SHA.

Bandit bloqueia achados de severidade média/alta com confiança média/alta. Trivy bloqueia vulnerabilidades altas/críticas identificadas, sem exclusões de CVEs ou uso de `ignore-unfixed`. A cobertura depende da distribuição: o scanner de pacotes [Alpine não cobre vulnerabilidades ainda sem correção](https://trivy.dev/docs/latest/coverage/os/alpine/). Os relatórios ficam nos artefatos da execução, mesmo se uma análise reprovar. O quadro "Security Gates" do dashboard lê `rede-alimenta-back/ia/seguranca.json`, que é gerado pelas ferramentas reais com `python ferramentas/gerar_seguranca.py` (Bandit, pip-audit, Gitleaks, Trivy e testes; o que não rodar fica como "não executado"). As configurações seguem as opções documentadas de [Bandit](https://bandit.readthedocs.io/en/latest/man/bandit.html) e [Trivy Action](https://github.com/aquasecurity/trivy-action).

Em 08/10/2026, o commit `df4e20c` passou nos dois jobs do [workflow DevSecOps](https://github.com/joaovitorxc/Alimenta-IA/actions/runs/37799988655). O histórico, as ferramentas e os limites dessa validação estão registrados em [DevSecOps e deploy](documentacao/05-devsecops-e-deploy.md). Nas próximas alterações, confira **Actions → DevSecOps** e os artefatos da execução correspondente.

O serviço está publicado no Render com deploy **manual** (`autoDeploy: false`), feito depois que o pipeline fica verde; não há deploy automático a partir do GitHub Actions. Dependências Python estão fixadas por versão exata; a imagem base usa tag Alpine/Python (digest registrado em `documentacao/05-devsecops-e-deploy.md`).
