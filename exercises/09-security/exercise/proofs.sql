-- Tarefa 2: provas dos privilégios de roles.sql. Correr como postgres, sem ON_ERROR_STOP
-- (as instruções que devem falhar têm de falhar sem parar o script):
--   docker compose exec -T postgres psql -U postgres -d ex09 -e < exercises/09-security/exercise/proofs.sql

SET ROLE ex09_app;
SELECT current_user;

-- Esperado: FALHA, "must be owner of table film" (ex09_app não é dono de nenhuma tabela).
DROP TABLE film;

-- Esperado: FUNCIONA, INSERT 0 1 (ex09_app tem INSERT em actor e USAGE na sequência do actor_id).
INSERT INTO actor (first_name, last_name) VALUES ('X', 'Y');

RESET ROLE;
SET ROLE ex09_readonly;
SELECT current_user;

-- Esperado: FUNCIONA, devolve 1000.
SELECT count(*) FROM film;

-- Esperado: FALHA, "permission denied for table actor" (ex09_readonly só tem SELECT).
INSERT INTO actor (first_name, last_name) VALUES ('X', 'Y');

RESET ROLE;

-- Extra: ex09_migrations pode criar tabelas, e as novas recebem os privilégios por omissão.
SET ROLE ex09_migrations;
-- Esperado: FUNCIONA.
CREATE TABLE ex09_probe (id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, note text);
RESET ROLE;

SET ROLE ex09_app;
-- Esperado: FUNCIONA, a tabela nova já tem INSERT para ex09_app (default privileges).
INSERT INTO ex09_probe (note) VALUES ('default privileges work') RETURNING id, note;
-- Esperado: FALHA, ex09_app não pode criar tabelas em public (REVOKE CREATE ... FROM PUBLIC).
CREATE TABLE ex09_should_fail (id integer);
RESET ROLE;

SET ROLE ex09_readonly;
-- Esperado: FUNCIONA, a tabela nova já tem SELECT para ex09_readonly.
SELECT id, note FROM ex09_probe;
RESET ROLE;

DROP TABLE ex09_probe;
DELETE FROM actor WHERE first_name = 'X' AND last_name = 'Y';
