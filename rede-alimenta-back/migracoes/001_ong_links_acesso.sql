-- Acesso de ONGs por link com codigo (sem senha). O codigo e calculado no servidor (HMAC de ong_id + versao);
-- esta tabela guarda apenas a versao vigente, para o administrador poder invalidar um link e gerar outro.
-- Migracao aditiva e idempotente: nao altera nem apaga nenhuma tabela existente.
CREATE TABLE IF NOT EXISTS ong_links_acesso (
    ong_id        BIGINT      PRIMARY KEY REFERENCES ongs(id) ON DELETE CASCADE,
    versao        INTEGER     NOT NULL DEFAULT 1 CHECK (versao >= 1),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
