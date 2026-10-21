"""Contrato OpenAPI da API local, derivado dos campos usados pelo servidor."""
from datetime import date, timedelta


SWAGGER_HTML = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Rede Alimenta — Swagger</title>
  <link rel="stylesheet" href="/docs/assets/swagger-ui.css">
</head>
<body>
  <p>Rede Alimenta — API. Use o botão Authorize com o API_TOKEN. Operações de escrita alteram o banco conectado.</p>
  <div id="swagger-ui"></div>
  <script src="/docs/assets/swagger-ui-bundle.js"></script>
  <script src="/docs/assets/swagger-init.js"></script>
</body>
</html>"""


def build_openapi(fields, edit, resources):
    optional = {"telefone", "categoria", "latitude", "longitude", "cnpj"}
    doacao_status = ["pendente", "disponivel", "reservada", "concluida", "cancelada"]
    match_status = ["pendente", "aceito", "recusado", "concluido"]
    examples = {
        "nome": "Instituição exemplo", "email": "contato@example.com",
        "telefone": "11999999999", "regiao": "Zona Sul", "latitude": -23.55,
        "longitude": -46.63, "capacidade_kg": 100, "doador_id": 1,
        "alimento": "Arroz", "categoria": "Grãos", "quantidade_kg": 10,
        "validade": (date.today() + timedelta(days=30)).isoformat(),
        "cnpj": "11222333000181", "doacao_id": 1, "ong_id": 1, "score_ia": 0.8, "prioridade": "alta",
    }

    def prop(field, resource, request=False):
        if field == "id" or field.endswith("_id"):
            result = {"type": "integer", "example": 1}
        elif field in {"quantidade_kg", "capacidade_kg", "score_ia", "latitude", "longitude"}:
            result = {"type": "number"}
            if field in {"quantidade_kg", "capacidade_kg"}:
                result.update(minimum=0, exclusiveMinimum=True)
            if field == "score_ia":
                result.update(minimum=0, maximum=1,
                              description="Score informado manualmente; não há inferência de IA.")
        else:
            result = {"type": "string"}
        if field == "validade":
            result["format"] = "date"
        if field in {"data_cadastro", "data_match"}:
            result["description"] = "Data ou timestamp ISO 8601, conforme o tipo no banco."
        if field == "status":
            result["enum"] = match_status if resource == "matches" else doacao_status
            result["example"] = "pendente" if resource == "matches" else "disponivel"
        if field == "prioridade":
            result["enum"] = ["baixa", "media", "alta"]
        if field in optional:
            result["nullable"] = True
        if request and field in examples:
            result["example"] = examples[field]
        return result

    def obj(properties, required=()):
        result = {"type": "object", "properties": properties}
        if required:
            result["required"] = list(required)
        return result

    def response(description, schema):
        return {"description": description,
                "content": {"application/json": {"schema": schema}}}

    error = obj({"error": {"type": "string"}}, ["error"])
    ok = obj({"ok": {"type": "boolean", "example": True}}, ["ok"])
    created = obj({"id": {"type": "integer", "example": 1}}, ["id"])
    errors = {code: response(description, error) for code, description in {
        "401": "Token ausente ou inválido.", "429": "Limite de requisições excedido.",
        "400": "Entrada inválida, registro inexistente ou configuração ausente.",
        "404": "Rota não encontrada.", "405": "Operação não suportada.",
        "503": "Falha no banco ou exceção não classificada.",
    }.items()}
    paths = {}
    schemas = {"Error": error, "Success": ok, "Created": created}
    for resource, (_, _, columns) in resources.items():
        schemas[resource] = obj({field: prop(field, resource) for field in columns}, columns)
        for suffix, selected in [("Create", fields[resource]), ("Update", edit[resource])]:
            schemas[resource + suffix] = obj(
                {field: prop(field, resource, request=True) for field in selected},
                [field for field in selected if field not in optional])

        def operation(method, summary, code, schema, body=None):
            result = {"tags": [resource], "summary": summary,
                      "operationId": method + "_" + resource,
                      "responses": {code: response("Sucesso", schema), **errors}}
            if body:
                result["requestBody"] = {"required": True,
                    "description": "Objeto JSON de até 65.536 bytes. PUT exige todos os campos obrigatórios de edição.",
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/" + body}}}}
            return result

        paths["/api/" + resource] = {
            "get": operation("list", "Listar " + resource, "200",
                             {"type": "array", "items": {"$ref": "#/components/schemas/" + resource}}),
            "post": operation("create", "Cadastrar " + resource, "201", created, resource + "Create"),
        }
        paths["/api/" + resource + "/{id}"] = {
            "parameters": [{"name": "id", "in": "path", "required": True,
                            "schema": {"type": "integer", "minimum": 1}}],
            "put": operation("update", "Editar " + resource, "200", ok, resource + "Update"),
            "delete": operation("delete", "Excluir " + resource, "200", ok),
        }
    loose = {"type": "object", "additionalProperties": True}
    lote = obj({"alimento_descricao": {"type": "string", "example": "pao frances", "maxLength": 200},
                "categoria": {"type": "string", "example": "padaria"},
                "quantidade_kg": {"type": "number", "example": 20},
                "dias_ate_validade": {"type": "number", "example": 1},
                "distancia_km": {"type": "number", "example": 4},
                "capacidade_disponivel_kg": {"type": "number", "example": 50}},
               ["alimento_descricao", "categoria", "quantidade_kg", "dias_ate_validade",
                "distancia_km", "capacidade_disponivel_kg"])
    schemas["LoteRisco"] = lote
    paths["/api/ia/risco"] = {"post": {
        "tags": ["ia"], "summary": "Classificar risco de descarte de um lote", "operationId": "ia_risco",
        "description": "Modelo treinado com dados simulados; não acessa o banco.",
        "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/LoteRisco"}}}},
        "responses": {"200": response("Risco e probabilidades por classe", loose), **errors}}}
    paths["/api/doacoes/{id}/recomendacoes"] = {
        "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer", "minimum": 1}}],
        "get": {"tags": ["ia"], "summary": "Recomendar ONGs para uma doação disponível", "operationId": "ia_recomendacoes",
                "responses": {"200": response("Até 5 ONGs ordenadas por score_ia", loose), **errors}}}
    id_param = [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer", "minimum": 1}}]
    for acao, resumo in (("aprovar", "Aprovar oferta pendente (passa a disponível)"), ("recusar", "Recusar oferta pendente (fica cancelada)")):
        paths["/api/doacoes/{id}/" + acao] = {"parameters": id_param, "post": {
            "tags": ["fluxo"], "summary": resumo, "operationId": "doacao_" + acao,
            "responses": {"200": response("Sucesso", ok), **errors}}}
    paths["/api/ongs/{id}/link"] = {"parameters": id_param, "get": {
        "tags": ["fluxo"], "summary": "Link de acesso da ONG ao portal (por código, sem senha)", "operationId": "ong_link",
        "responses": {"200": response("Caminho do link", obj({"caminho": {"type": "string", "example": "/ong#1.codigo"}})), **errors}}}
    paths["/api/ongs/{id}/link/renovar"] = {"parameters": id_param, "post": {
        "tags": ["fluxo"], "summary": "Invalidar o link atual da ONG e gerar outro", "operationId": "ong_link_renovar",
        "responses": {"200": response("Novo caminho", obj({"caminho": {"type": "string"}})), **errors}}}
    oferta = obj({"nome": {"type": "string"}, "email": {"type": "string"}, "telefone": {"type": "string", "nullable": True},
                  "regiao": {"type": "string"}, "alimento": {"type": "string", "example": "Pão francês"},
                  "categoria": {"type": "string", "enum": ["hortifruti", "padaria", "laticinios", "carnes", "prontos", "nao_perecivel"]},
                  "quantidade_kg": {"type": "number", "minimum": 0.01, "maximum": 10000},
                  "validade": {"type": "string", "format": "date"}, "aceite": {"type": "boolean", "enum": [True]},
                  "site": {"type": "string", "description": "Campo-armadilha: deve ficar vazio."}},
                 ["nome", "email", "regiao", "alimento", "categoria", "quantidade_kg", "validade", "aceite"])
    schemas["OfertaPublica"] = oferta
    paths["/api/publico/doacoes"] = {"post": {
        "tags": ["publico"], "summary": "Enviar oferta de doação (sem token; entra como pendente)", "operationId": "oferta_publica",
        "description": "Rota pública. Limites: 5 ofertas por IP por hora e 100 por hora no total; corpo de até 8 KiB, application/json. "
                       "A oferta fica em ofertas_publicas e só vira doador e doação quando o gestor aprova.",
        "security": [],
        "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/OfertaPublica"}}}},
        "responses": {"201": response("Oferta recebida", obj({"mensagem": {"type": "string"}, "codigo": {
                          "type": "string", "description": "Código de acompanhamento (aparece uma vez; o banco guarda só o hash). "
                          "Ausente se o banco ainda não tem a migração 005."}})),
                      "400": response("Dados inválidos ou alimento/categoria recusados.", error),
                      "429": response("Limite de ofertas excedido.", error), "503": response("Validação indisponível.", error)}}}
    paths["/api/publico/ong-acesso"] = {"post": {
        "tags": ["publico"], "summary": "ONG pede acesso ao portal (sem token; o administrador analisa e envia o link)", "operationId": "pedido_acesso_ong",
        "description": "Rota pública. Limites: 3 pedidos por IP por hora e 30 por hora no total; corpo de até 8 KiB. A resposta é sempre a mesma.",
        "security": [],
        "requestBody": {"required": True, "content": {"application/json": {"schema": obj(
            {"nome": {"type": "string"}, "email": {"type": "string"}, "telefone": {"type": "string", "nullable": True},
             "regiao": {"type": "string"}, "mensagem": {"type": "string", "maxLength": 500, "nullable": True},
             "cnpj": {"type": "string", "nullable": True, "description": "Opcional; os dígitos verificadores são conferidos."},
             "capacidade_kg": {"type": "number", "nullable": True, "description": "Opcional; capacidade aproximada de recebimento."},
             "aceite": {"type": "boolean", "enum": [True]}, "site": {"type": "string", "description": "Campo-armadilha: deve ficar vazio."}},
            ["nome", "email", "regiao", "aceite"])}}},
        "responses": {"201": response("Pedido recebido", obj({"mensagem": {"type": "string"}})),
                      "400": response("Dados inválidos.", error), "429": response("Limite de pedidos excedido.", error)}}}
    paths["/api/publico/acompanhar"] = {"post": {
        "tags": ["publico"], "summary": "Acompanhar uma oferta pelo código recebido ao enviá-la (sem token)", "operationId": "acompanhar_oferta",
        "description": "Rota pública. O código (128 bits, guardado só como hash) vai no corpo para não aparecer em logs nem em URLs. "
                       "20 códigos inválidos por IP em 10 minutos bloqueiam novas tentativas. Não devolve dados pessoais.",
        "security": [],
        "requestBody": {"required": True, "content": {"application/json": {"schema": obj({"codigo": {"type": "string"}}, ["codigo"])}}},
        "responses": {"200": response("Situação da oferta", loose), "404": response("Código não encontrado.", error),
                      "429": response("Muitas tentativas inválidas.", error)}}}
    paths["/api/ofertas"] = {"get": {
        "tags": ["fluxo"], "summary": "Ofertas da página pública aguardando análise", "operationId": "listar_ofertas",
        "responses": {"200": response("Ofertas pendentes", loose), **errors}}}
    for acao, texto in (("aprovar", "cria o doador e a doação disponível"), ("recusar", "apaga os dados pessoais da oferta")):
        paths["/api/ofertas/{id}/" + acao] = {"parameters": id_param, "post": {
            "tags": ["fluxo"], "summary": "Oferta pública: " + acao + " (" + texto + ")", "operationId": "oferta_" + acao,
            "responses": {"200": response("Sucesso", ok), **errors}}}
    paths["/api/ong-solicitacoes"] = {"get": {
        "tags": ["fluxo"], "summary": "Pedidos de acesso de ONGs aguardando análise", "operationId": "listar_solicitacoes_ong",
        "responses": {"200": response("Pedidos pendentes", loose), **errors}}}
    for acao in ("atender", "descartar"):
        paths["/api/ong-solicitacoes/{id}/" + acao] = {"parameters": id_param, "post": {
            "tags": ["fluxo"], "summary": "Encerrar um pedido de acesso (" + acao + ")", "operationId": "solicitacao_ong_" + acao,
            "responses": {"200": response("Sucesso", ok), **errors}}}
    portal_headers = [{"name": "X-Ong-Id", "in": "header", "required": True, "schema": {"type": "integer"}},
                      {"name": "X-Ong-Codigo", "in": "header", "required": True, "schema": {"type": "string"}}]
    paths["/api/ong-portal/matches"] = {"get": {
        "tags": ["publico"], "summary": "Portal da ONG: matches indicados para ela", "operationId": "portal_ong_matches",
        "description": "Autenticado por link com código (cabeçalhos X-Ong-Id e X-Ong-Codigo). O contato do doador só aparece após o aceite.",
        "security": [], "parameters": portal_headers,
        "responses": {"200": response("Matches da ONG", loose), "401": response("Link inválido ou expirado.", error), "429": response("Muitas tentativas.", error)}}}
    for acao, resumo in (("aceitar", "aceitar um match pendente"), ("recusar", "recusar um match pendente"),
                         ("receber", "confirmar o recebimento de um match aceito (conclui a entrega)")):
        paths["/api/ong-portal/matches/{id}/" + acao] = {"parameters": [*id_param, *portal_headers], "post": {
            "tags": ["publico"], "summary": "Portal da ONG: " + resumo, "operationId": "portal_ong_" + acao,
            "security": [],
            "responses": {"200": response("Sucesso", ok), "400": response("Match de outra ONG, inexistente ou já respondido.", error),
                          "401": response("Link inválido ou expirado.", error)}}}
    paths["/api/indicadores"] = {"get": {
        "tags": ["ia"], "summary": "Indicadores do dashboard (impacto, IA e segurança)", "operationId": "indicadores",
        "responses": {"200": response("Indicadores agregados", loose), **errors}}}
    return {
        "openapi": "3.0.3",
        "info": {"title": "Rede Alimenta — API local", "version": "1.0.0",
                 "description": "CRUD de doadores, ONGs, doações e matches. Exige token Bearer (API_TOKEN). "
                 "A execução de operações de escrita altera o banco configurado em DATABASE_URL. "
                 "IDs nos exemplos são ilustrativos e precisam existir no banco. "
                 "Dados sem sentido (alimento, categoria, datas, quantidades) são recusados. Rotas /api/publico e /api/ong-portal não usam o token do gestor."},
        "servers": [{"url": "/", "description": "Servidor que fornece esta documentação"}],
        "tags": [{"name": resource} for resource in [*resources, "ia", "fluxo", "publico"]],
        "paths": paths,
        "security": [{"bearerAuth": []}],
        "components": {"schemas": schemas,
                       "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}},
    }
