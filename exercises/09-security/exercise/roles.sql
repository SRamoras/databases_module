-- Tarefa 1: roles com privilégio mínimo em ex09. Correr como postgres, com as palavras-passe
-- passadas como variáveis do psql (nunca escritas neste ficheiro):
--   docker compose exec -T postgres psql -U postgres -d ex09 -v ON_ERROR_STOP=1 \
--     -v migrations_password="$EX09_MIGRATIONS_PASSWORD" -v app_password="$EX09_APP_PASSWORD" \
--     -v readonly_password="$EX09_READONLY_PASSWORD" < exercises/09-security/exercise/roles.sql
-- Pode correr mais do que uma vez.

-- Os roles são do servidor inteiro, por isso só se criam se ainda não existirem.
SELECT format('CREATE ROLE %I LOGIN', name)
FROM unnest(ARRAY['ex09_migrations', 'ex09_app', 'ex09_readonly']) AS name
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = name)
\gexec

ALTER ROLE ex09_migrations LOGIN PASSWORD :'migrations_password';
ALTER ROLE ex09_app        LOGIN PASSWORD :'app_password';
ALTER ROLE ex09_readonly   LOGIN PASSWORD :'readonly_password';

-- ex09_migrations é o dono da base de dados.
ALTER DATABASE ex09 OWNER TO ex09_migrations;

-- Ninguém mais cria tabelas em public. No Pagila o dono do schema public é postgres
-- (não pg_database_owner), por isso ser dono da base de dados não chega: ex09_migrations
-- recebe CREATE explicitamente, e é o único role (além do superutilizador) que o tem.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO ex09_migrations;
GRANT USAGE ON SCHEMA public TO ex09_app, ex09_readonly;

-- ex09_app: ler e escrever dados, e usar as sequências (para as chaves geradas nos INSERT).
-- Sem DROP, ALTER, TRUNCATE nem CREATE.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ex09_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO ex09_app;

-- ex09_readonly: só ler.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ex09_readonly;

-- As tabelas e sequências que ex09_migrations criar no futuro recebem os mesmos privilégios.
ALTER DEFAULT PRIVILEGES FOR ROLE ex09_migrations IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ex09_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ex09_migrations IN SCHEMA public
    GRANT USAGE ON SEQUENCES TO ex09_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ex09_migrations IN SCHEMA public
    GRANT SELECT ON TABLES TO ex09_readonly;
