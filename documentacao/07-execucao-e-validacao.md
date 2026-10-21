# Execução e validação

## Iniciar no Windows

Na raiz `Alimenta-IA`, com Python instalado:

```powershell
# Somente se o ambiente virtual ainda não existir:
python -m venv .venv

.\.venv\Scripts\python.exe -m pip install -r .\rede-alimenta-back\requirements.txt
```

Criar localmente `rede-alimenta-back/.env`, sem adicionar credenciais ao Git:

```dotenv
DATABASE_URL=postgresql://USUARIO:SENHA@HOST:PORTA/BANCO
API_TOKEN=gere-com-python-c-import-secrets-print-secrets-token_urlsafe-32
```

`API_TOKEN` (32+ caracteres) é obrigatório; o painel pede esse token ao abrir. No Supabase, prefira a string do Session pooler (funciona em IPv4).

Substituir os marcadores pela configuração do banco. Usar a configuração de transporte exigida pelo provedor. Para criar as tabelas em um banco vazio (ou conferir um existente), rode `cd rede-alimenta-back; ..\.venv\Scripts\python.exe migrar.py` (aplica `database/schema.sql` e as migrações; idempotente). Para ter números no dashboard em um banco **local**, rode também `python demo_seed.py` (veja o README).

```powershell
cd rede-alimenta-back
..\.venv\Scripts\python.exe server.py
```

Abrir `http://localhost:8000` (página inicial pública; painel do gestor em `/admin`) e manter o terminal em execução. Encerrar com `Ctrl+C`. Node/npm não são necessários para o frontend atual. Não é preciso ativar o ambiente virtual quando se chama seu executável diretamente.

## Roteiro de validação proposto

Usar banco de teste e registros sintéticos. O roteiro abaixo ainda não foi executado como parte desta documentação.

| ID | Caso | Resultado esperado |
|---|---|---|
| V01 | Abrir raiz, CSS e JavaScript | Arquivos servidos e painel renderizado |
| V02 | Listar os quatro recursos em banco preparado | 200 com arrays no formato documentado |
| V03 | Criar doador e ONG com dados válidos | 201 com IDs; registros aparecem no painel |
| V04 | Criar doação com quantidade zero ou validade passada | 400; registro não criado |
| V05 | Criar doação válida e match com IDs existentes | 201; vínculos apresentados corretamente |
| V06 | Criar match com score fora de 0–1 | 400 |
| V07 | Editar dados permitidos e status válidos | 200; valores persistidos |
| V08 | Editar status fora da lista | 400 |
| V09 | Excluir registros de teste em ordem compatível com vínculos | 200; registros removidos |
| V10 | Buscar texto e filtrar status no frontend | Lista corresponde aos filtros |
| V11 | Simular indisponibilidade do banco | Mensagem de falha e opção de atualizar; registrar status real |
| V12 | Enviar corpo acima do limite POST/PUT | 400 |

Testes automatizados (sem banco): `cd rede-alimenta-back && python -m unittest discover -s tests -v` cobre autenticação, limites, cabeçalhos, Swagger local, IA, recomendação e indicadores com dados simulados; `python -m unittest discover -s ml/tests` confere o modelo. Autorização por usuário e teste de carga continuam pendentes. Não executar mutações contra dados reais para preencher evidências acadêmicas.

## Registro de evidência

Para cada caso: data, responsável, commit, ambiente, entrada sem dados pessoais, resultado obtido, aprovado/reprovado e link de captura ou log sanitizado. Separar o resultado esperado do resultado obtido. Falhas devem gerar ação de correção e nova evidência.

## Problemas comuns

- `DATABASE_URL` ausente: conferir o arquivo local e reiniciar o servidor após alterar a configuração.
- Tabela ou coluna inexistente: rode `python migrar.py` para criar o esquema e as migrações.
- Porta ocupada: encerrar o servidor anterior ou ajustar conscientemente sua configuração.
- Página aberta como arquivo: acessar pelo servidor em localhost.
- Erro ao remover registro vinculado: revisar constraints e regra de exclusão do banco; não presumir cascata.

## Evidência de validação (14 e 15/10/2026)

Execução assistida por Claude Code, a pedido da equipe, em bancos PostgreSQL locais descartáveis (Docker), com dados sintéticos; o banco do Supabase não foi alterado por esses testes. Navegador automatizado (Chromium) em tela de computador (1366 px) e de celular (390 px). Os scripts de verificação não fazem parte do repositório.

| Caso | Resultado obtido |
|---|---|
| Servidor em banco **vazio** | Cria sozinho as 8 tabelas (esquema + migrações 001 a 006); repetir não dá erro |
| Páginas `/`, `/doar`, `/acompanhar`, `/ong`, `/privacidade`, `/admin`, `/docs` | 200; sem erros no console. Um erro de CSP (rótulos do mapa com estilo inline) foi achado nesta rodada, corrigido e virou teste automatizado |
| Oferta pública | 201 com código de acompanhamento; **nenhum doador nem doação criado**; oferta repetida recusada (400); campos inválidos recusados |
| Acompanhamento pelo código | Etapas "analisando", "procurando ONG", "ONG indicada", "ONG aceitou (com o nome da ONG)", "entregue" e "recusada"; sem dados pessoais; código errado responde 404; 21ª tentativa inválida do mesmo IP recebe 429 |
| Aprovar e recusar ofertas | Aprovar cria o doador e a doação disponível e não pode ser repetido (400); recusar apaga nome, e-mail, telefone e região e não cria doador |
| Recomendação com distância | Mesmo lote: ONG a ~6 km com score 55% e ONG a ~84 km com score 26%; a mais perto vem primeiro; distância acima de 25 km marcada. Antes do ajuste da faixa do treino, a ONG distante ficava com ~100% (corrigido) |
| Portal da ONG | Aceitar libera o contato do doador; receber antes de aceitar é recusado (400); **confirmar recebimento** conclui a entrega e a doação; a confirmação some do botão e o cartão vai para "Concluídas" |
| Indicadores | kg salvos, refeições por **região da ONG**, posição no mapa (coordenadas da ONG), entregas confirmadas pela ONG e tempo médio contado desde o envio da oferta |
| Banco **sem** as migrações 005 e 006 | Oferta cai no fluxo antigo (201 sem código); `/api/ofertas` vazio; aprovar pela fila antiga funciona; a ONG conclui a entrega sem a tabela de confirmações; indicadores e recomendações respondem normalmente |
| Migração automática em banco que já tinha dados | Tabelas novas criadas, dados mantidos; com uma trava de 12 s em outra sessão, a migração falha em ~5 s, é registrada no log e o servidor segue respondendo |
| Pedidos de acesso de ONGs | Descartar apaga os dados pessoais; atender mantém o registro |
| Dashboard com dados de demonstração (`demo_seed.py`) | Kg salvos, refeições, tempo médio de match, entregas confirmadas pela ONG, mapa do Brasil com detalhe ampliado, mapa de calor e Security Gates, em computador e celular; sem erros |
| Fluxo no navegador | Painel com fila de ofertas, recomendação com coluna de distância, "Avisar ONG" (e-mail e WhatsApp com a mensagem pronta), página de acompanhamento em vários estados, envio de oferta com código e confirmação de recebimento no portal |
| Contas e perfis (banco real) | Gestor cria conta de gestor e de ONG e recebe a senha provisória uma vez; a provisória só deixa trocar a senha (403 nas demais rotas) e a senha fraca é recusada; depois da troca a senha antiga deixa de valer; e-mail repetido (com outra caixa) recusado; conta de ONG recebe 403 no painel, em Acessos e em Auditoria e vê só a própria ONG no portal |
| Login | Senha errada, e-mail inexistente e conta desativada têm a mesma resposta; 5 falhas bloqueiam o e-mail (429), inclusive um e-mail que não existe; sessão de conta desativada cai na hora; sair encerra a sessão; o `API_TOKEN` e a senha antiga do painel **não** entram mais pelo login (401), e sessões antigas `s1…` são recusadas |
| Link como convite | Pessoa da ONG cria a própria conta pelo link (senha fraca recusada, já entra logada, o código sai da barra de endereço); quem já tem conta não cria outra; o gestor desativa o link (401 no link, a conta continua entrando) e gerar um link novo reativa |
| Auditoria | Registra quem fez o quê (conta, token da API, link da ONG), logins bons e ruins; sem senhas nem corpo das requisições |
| Banco sem a migração 007 | O portal por link segue funcionando; login por e-mail e Acessos avisam que faltam as tabelas; renovar link funciona e desativar link avisa |
| Navegador (computador e celular) | Login com e-mail, diálogo obrigatório de primeira senha (Esc não fecha), Minha conta, páginas Acessos e Auditoria, senha provisória com botão Copiar, portal da ONG com entrar, criar conta pelo link, alterar senha e sair |
| Testes automatizados | 212 aprovados (`python -m unittest discover -s tests`) e 1 de equivalência do modelo (`ml/tests`) |

Não foram executados nesta rodada: V11 (queda do banco no meio de uma operação), teste de carga e teste com o Supabase real (o banco da nuvem só foi consultado em modo leitura para extrair o esquema).
