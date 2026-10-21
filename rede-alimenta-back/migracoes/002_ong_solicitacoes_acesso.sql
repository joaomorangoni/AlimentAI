-- Pedidos de acesso ao portal feitos por ONGs (pagina publica). O administrador analisa e, se aprovar, envia o link.
-- Migracao aditiva e idempotente: nao altera nem apaga nenhuma tabela existente.
CREATE TABLE IF NOT EXISTS ong_solicitacoes_acesso (
    id          BIGSERIAL   PRIMARY KEY,
    nome        VARCHAR(120) NOT NULL,
    email       VARCHAR(160) NOT NULL,
    telefone    VARCHAR(20),
    regiao      VARCHAR(80)  NOT NULL,
    mensagem    VARCHAR(500),
    status      VARCHAR(12)  NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'atendida', 'descartada')),
    criado_em   TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ong_solicitacoes_acesso_status_idx ON ong_solicitacoes_acesso (status, id);
