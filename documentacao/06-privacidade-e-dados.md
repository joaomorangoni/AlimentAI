# Privacidade e proteção de dados

Plano inicial para o requisito de LGPD do checkpoint 3. A aplicação não teve sua conformidade jurídica ou operacional validada. As decisões abaixo devem ser definidas pela equipe e pela organização responsável antes de usar dados reais ou publicar o serviço.

## Inventário inicial

| Dados | Finalidade prevista | Situação e ação |
|---|---|---|
| Nome, e-mail e telefone do doador | Avaliar a oferta e combinar a coleta | A oferta fica em `ofertas_publicas` até a decisão: **só a aprovação cria o doador**; recusar **apaga** nome, e-mail, telefone e região; a API lista contatos só com token do gestor; o contato só chega à ONG depois do aceite |
| Contas de gestor e de pessoas de ONG (nome, e-mail, hash da senha, último acesso) | Controlar quem entra no painel e no portal | Senha só como hash PBKDF2; a conta pode ser desativada (as sessões caem na hora); visível só ao gestor |
| Trilha de auditoria (quem fez qual ação, quando; IP apenas nos logins) | Segurança e responsabilização | Não guarda corpo de requisição, senha nem o e-mail digitado em login recusado; visível só ao gestor; retenção ainda a definir |
| Código de acompanhamento da oferta | Permitir que o doador veja a situação sem conta | Aleatório (128 bits); o banco guarda só o hash; a página mostra etapa, alimento, quantidade e o nome da ONG que aceitou; sem dados pessoais |
| Nome e contatos da ONG | Cadastro e coordenação | Contatos de representantes podem identificar pessoas; restringir exposição |
| Região e coordenadas | Compatibilidade logística | Coordenadas podem identificar endereço; reduzir precisão em telas públicas |
| Doações e matches vinculados | Gestão e acompanhamento | Definir retenção e evitar divulgação de histórico individual |
| Pedido de acesso de ONG (nome, e-mail, telefone, região, CNPJ opcional, capacidade, mensagem) | Analisar o pedido e cadastrar a organização | CNPJ guardado só com dígitos; sem retorno automático de dados; fila visível só ao gestor; **descartar apaga os dados pessoais** do pedido |
| Logs e futura auditoria | Segurança e operação | Minimizar dados, controlar acesso e definir retenção |

## Decisões pendentes

- Controlador (para fins do aviso): a equipe do projeto (Davi Oliveira da Silva, João Pedro Morangoni e João Vitor Xavier de Carvalho); operadores: Supabase (banco) e Render (aplicação). Falta formalizar um contato de privacidade dedicado.
- Definir finalidade e fundamento aplicável a cada tratamento, com revisão competente.
- ~~Criar aviso de privacidade compreensível e canal para solicitações dos titulares.~~ **Feito:** página pública `/privacidade`, ligada aos formulários de oferta e de pedido de acesso, com canal de solicitações (Issues do repositório ou integrantes da equipe). O aviso descreve o código de acompanhamento e o apagamento dos dados de ofertas recusadas e de pedidos descartados.
- Definir prazo de retenção, exclusão, anonimização e tratamento de backups.
- Avaliar provedores, acessos, localização dos dados e contratos aplicáveis.
- Definir resposta a incidente, responsáveis, registro e avaliação de comunicações necessárias.

## Medidas técnicas propostas

Já implementado: acesso à API restrito por token Bearer, cabeçalhos de segurança e logs sem token nem conteúdo de requisições. Pendente: autenticar usuários individualmente; autorizar acesso por função e organização; proteger transporte e segredos; limitar permissões de banco; auditar alterações sem registrar senha ou string de conexão; usar dados sintéticos em demonstrações. Revisar acesso e backups periodicamente.

Para dashboard e pitch, apresentar agregados regionais e impedir identificação de pessoas por combinações de região, coordenadas e pequenos grupos. Não incluir dados de beneficiários sem necessidade definida e análise adicional.

## Evidências a produzir

Inventário revisado, decisões de tratamento, aviso de privacidade, procedimento de solicitação/exclusão, revisão de acesso, teste de restauração e simulação de incidente. Datas, responsáveis e resultados devem ser registrados após execução.
