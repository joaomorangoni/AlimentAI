-- Esquema base da Rede Alimenta: so as quatro tabelas que este codigo usa (doadores, ongs, doacoes, matches).
-- Foi conferido contra o banco Supabase da equipe (tipos, chaves e indices). Idempotente: CREATE ... IF NOT EXISTS
-- nao altera tabelas que ja existem. Aplique com `python migrar.py` (roda este arquivo e depois migracoes/*.sql).
-- Os dados pessoais vivem aqui; veja documentacao/06-privacidade-e-dados.md.

CREATE TABLE IF NOT EXISTS doadores (
    id        BIGSERIAL    PRIMARY KEY,
    nome      VARCHAR(150) NOT NULL,
    email     VARCHAR(150) NOT NULL UNIQUE,
    telefone  VARCHAR(20),
    regiao    VARCHAR(100),
    latitude  NUMERIC(9, 6),
    longitude NUMERIC(9, 6),
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ongs (
    id            BIGSERIAL    PRIMARY KEY,
    nome          VARCHAR(150) NOT NULL,
    email         VARCHAR(150) NOT NULL UNIQUE,
    telefone      VARCHAR(20),
    regiao        VARCHAR(100),
    latitude      NUMERIC(9, 6),
    longitude     NUMERIC(9, 6),
    capacidade_kg NUMERIC(10, 2),
    criado_em     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS doacoes (
    id            BIGSERIAL     PRIMARY KEY,
    doador_id     BIGINT        NOT NULL,
    alimento      VARCHAR(150)  NOT NULL,
    categoria     VARCHAR(100),
    quantidade_kg NUMERIC(10, 2) NOT NULL,
    validade      DATE          NOT NULL,
    status        VARCHAR(30)   DEFAULT 'disponivel',
    data_cadastro TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_doacao_doador FOREIGN KEY (doador_id) REFERENCES doadores (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS doacoes_doador_idx ON doacoes (doador_id);

CREATE TABLE IF NOT EXISTS matches (
    id         BIGSERIAL   PRIMARY KEY,
    doacao_id  BIGINT      NOT NULL,
    ong_id     BIGINT      NOT NULL,
    score_ia   NUMERIC(5, 4),
    prioridade VARCHAR(30),
    status     VARCHAR(30) DEFAULT 'pendente',
    data_match TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_match_doacao FOREIGN KEY (doacao_id) REFERENCES doacoes (id) ON DELETE CASCADE,
    CONSTRAINT fk_match_ong    FOREIGN KEY (ong_id)    REFERENCES ongs (id)    ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS matches_ong_idx ON matches (ong_id);
-- Uma doacao so pode ter um match aceito/concluido; e nao se repete o par (doacao, ONG) pendente.
CREATE UNIQUE INDEX IF NOT EXISTS matches_reserva_unica ON matches (doacao_id) WHERE status IN ('aceito', 'concluido');
CREATE UNIQUE INDEX IF NOT EXISTS matches_pendente_unico ON matches (doacao_id, ong_id) WHERE status = 'pendente';
