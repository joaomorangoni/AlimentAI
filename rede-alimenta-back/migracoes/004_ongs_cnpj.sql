-- CNPJ opcional no cadastro da ONG (so digitos). Unico quando informado; ONGs sem CNPJ continuam validas.
-- Migracao aditiva e idempotente.
ALTER TABLE ongs ADD COLUMN IF NOT EXISTS cnpj CHAR(14);
CREATE UNIQUE INDEX IF NOT EXISTS ongs_cnpj_unico ON ongs (cnpj) WHERE cnpj IS NOT NULL;
