-- Dados opcionais do pedido de acesso, para o administrador avaliar a organizacao (CNPJ so com digitos).
-- Migracao aditiva e idempotente.
ALTER TABLE ong_solicitacoes_acesso ADD COLUMN IF NOT EXISTS cnpj CHAR(14);
ALTER TABLE ong_solicitacoes_acesso ADD COLUMN IF NOT EXISTS capacidade_kg NUMERIC(10, 2);
