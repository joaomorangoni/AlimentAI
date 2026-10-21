-- Quem confirmou a entrega de um match: a propria ONG (portal) ou o gestor. Permite mostrar no dashboard quantas entregas
-- foram confirmadas por quem recebeu. Migracao aditiva e idempotente; nao altera a tabela matches.
CREATE TABLE IF NOT EXISTS match_confirmacoes (
    match_id      BIGINT      PRIMARY KEY REFERENCES matches (id) ON DELETE CASCADE,
    origem        VARCHAR(10) NOT NULL CHECK (origem IN ('ong', 'gestor')),
    confirmado_em TIMESTAMPTZ  NOT NULL DEFAULT now()
);
