-- Endereços estruturados dos dois formulários públicos. Registros antigos continuam válidos.
ALTER TABLE ofertas_publicas ADD COLUMN IF NOT EXISTS endereco JSONB;
ALTER TABLE ong_solicitacoes_acesso ADD COLUMN IF NOT EXISTS endereco JSONB;
