-- Contas individuais (gestor e ONG), sessoes e trilha de auditoria. Os nomes nao colidem com as tabelas de contas que o
-- banco da equipe ja tem (ong_contas, doador_contas, ong_sessoes...), que este codigo nao usa. Senhas so como hash
-- PBKDF2; sessoes so como hash SHA-256. Migracao aditiva e idempotente.
CREATE TABLE IF NOT EXISTS usuarios (
    id            BIGSERIAL    PRIMARY KEY,
    perfil        VARCHAR(10)  NOT NULL CHECK (perfil IN ('gestor', 'ong')),
    ong_id        BIGINT       REFERENCES ongs (id) ON DELETE CASCADE,
    nome          VARCHAR(120) NOT NULL,
    email         VARCHAR(160) NOT NULL,
    senha_hash    TEXT         NOT NULL,
    ativo         BOOLEAN      NOT NULL DEFAULT TRUE,
    trocar_senha  BOOLEAN      NOT NULL DEFAULT FALSE,
    criado_em     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    ultimo_acesso TIMESTAMPTZ,
    CONSTRAINT usuarios_perfil_ong CHECK ((perfil = 'ong') = (ong_id IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS usuarios_email_unico ON usuarios (lower(email));
CREATE INDEX IF NOT EXISTS usuarios_ong_idx ON usuarios (ong_id);

CREATE TABLE IF NOT EXISTS usuario_sessoes (
    token_hash CHAR(64)    PRIMARY KEY,
    usuario_id BIGINT      NOT NULL REFERENCES usuarios (id) ON DELETE CASCADE,
    criado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expira_em  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS usuario_sessoes_usuario_idx ON usuario_sessoes (usuario_id);
CREATE INDEX IF NOT EXISTS usuario_sessoes_expira_idx ON usuario_sessoes (expira_em);

CREATE TABLE IF NOT EXISTS auditoria_acoes (
    id          BIGSERIAL    PRIMARY KEY,
    quando      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    ator_tipo   VARCHAR(10)  NOT NULL,
    ator_id     BIGINT,
    ator_nome   VARCHAR(160) NOT NULL,
    acao        VARCHAR(120) NOT NULL,
    recurso     VARCHAR(40),
    registro_id BIGINT,
    ip          VARCHAR(45)
);
CREATE INDEX IF NOT EXISTS auditoria_acoes_id_idx ON auditoria_acoes (id DESC);

-- O gestor pode desativar o link de uma ONG que ja tem contas, sem gerar um link novo.
ALTER TABLE ong_links_acesso ADD COLUMN IF NOT EXISTS ativo BOOLEAN NOT NULL DEFAULT TRUE;
