-- Ofertas enviadas pela pagina publica ficam aqui ate o gestor decidir. So a aprovacao cria o doador e a doacao;
-- assim, visitantes que nunca foram aprovados nao viram "doadores". Recusar apaga os dados pessoais da oferta.
-- O codigo de acompanhamento (que o doador recebe ao enviar) e guardado apenas como hash. Os momentos usam TIMESTAMPTZ para o
-- navegador mostrar a hora certa em qualquer fuso. Migracao aditiva e idempotente.
CREATE TABLE IF NOT EXISTS ofertas_publicas (
    id            BIGSERIAL     PRIMARY KEY,
    codigo_hash   CHAR(64)      NOT NULL UNIQUE,
    nome          VARCHAR(150)  NOT NULL,
    email         VARCHAR(150)  NOT NULL,
    telefone      VARCHAR(20),
    regiao        VARCHAR(100),
    alimento      VARCHAR(150)  NOT NULL,
    categoria     VARCHAR(100)  NOT NULL,
    quantidade_kg NUMERIC(10, 2) NOT NULL,
    validade      DATE          NOT NULL,
    status        VARCHAR(12)   NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'aprovada', 'recusada')),
    doacao_id     BIGINT        REFERENCES doacoes (id) ON DELETE SET NULL,
    criado_em     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    decidido_em   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ofertas_publicas_status_idx ON ofertas_publicas (status, id);
CREATE INDEX IF NOT EXISTS ofertas_publicas_email_idx ON ofertas_publicas (email);
