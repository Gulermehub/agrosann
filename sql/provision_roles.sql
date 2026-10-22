-- Executar uma única vez como administrador do PostgreSQL, com psql.
-- As senhas vêm do ambiente e não devem ser versionadas.
\getenv owner_password AGROSAN_OWNER_PASSWORD
\getenv app_password AGROSAN_APP_PASSWORD
CREATE ROLE agrosan_owner LOGIN PASSWORD :'owner_password';
CREATE ROLE agrosan_app LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE DATABASE agrosan OWNER agrosan_owner;
REVOKE ALL ON DATABASE agrosan FROM PUBLIC;
GRANT CONNECT ON DATABASE agrosan TO agrosan_app;
