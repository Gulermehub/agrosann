-- Executar depois de init-db, conectado ao banco agrosan como owner/admin.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO agrosan_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON lotes, animais, vacinacao, manejo_sanitario, login_attempts TO agrosan_app;
GRANT SELECT, INSERT ON usuarios, audit_log TO agrosan_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO agrosan_app;
GRANT EXECUTE ON FUNCTION status_vacinacao(TEXT) TO agrosan_app;
