-- Função de negócio demonstrável no Banco de Dados II.
CREATE OR REPLACE FUNCTION status_vacinacao(proxima_dose TEXT)
RETURNS TEXT LANGUAGE SQL STABLE AS $$
 SELECT CASE WHEN proxima_dose IS NULL THEN 'Sem agendamento'
 WHEN proxima_dose::date < CURRENT_DATE THEN 'Atrasada'
 WHEN proxima_dose::date = CURRENT_DATE THEN 'Hoje' ELSE 'Em dia' END
$$;
-- SECURITY DEFINER permite ao app inserir registros por trigger sem alterar logs antigos.
CREATE OR REPLACE FUNCTION registrar_auditoria() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
BEGIN
 INSERT INTO public.audit_log (acao, detalhes)
 VALUES (TG_OP || '_' || TG_TABLE_NAME, 'Registro ID: ' || CASE WHEN TG_OP = 'DELETE' THEN OLD.id ELSE NEW.id END);
 RETURN NULL;
END;
$$;
DO $$
DECLARE t TEXT;
BEGIN
 FOREACH t IN ARRAY ARRAY['animais','lotes','vacinacao','manejo_sanitario'] LOOP
 EXECUTE format('DROP TRIGGER IF EXISTS trg_auditoria ON %I', t);
 EXECUTE format('CREATE TRIGGER trg_auditoria AFTER INSERT OR UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION registrar_auditoria()', t);
 END LOOP;
END;
$$;
REVOKE ALL ON FUNCTION registrar_auditoria() FROM PUBLIC;
