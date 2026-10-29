# Exercício 09: Privilégio mínimo nos três motores e uma API sem injeção

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `roles.sql` | Tarefa 1: roles `ex09_migrations`, `ex09_app` e `ex09_readonly` e os seus privilégios |
| `proofs.sql` | Tarefa 2: provas com `SET ROLE` / `RESET ROLE`, com o resultado esperado em comentário |
| `api/` | Tarefa 3: API em FastAPI (projeto uv) |
| `api/.env.example` | As variáveis de ambiente de que a API e os scripts precisam |
| `api/app/main.py` | Os 3 endpoints |
| `api/app/clients.py` | As ligações aos três motores, só com as credenciais da aplicação |
| `api/scripts/setup_mongo.py` | Cria o utilizador MongoDB `ex09_app` e a coleção `notes` com validação |
| `api/scripts/setup_redis.py` | Cria o utilizador ACL do Redis `ex09_app` |

## O que o enunciado não diz

O enunciado tem só 4 tarefas, mas a tarefa 3 fala dos "utilizadores das tarefas 1 e 3", e as entregas pedem o output das "tarefas 5 e 6" e falam do `ACL SETUSER`. Interpretei assim:
- **Utilizadores MongoDB e Redis:** a tarefa 3 também cria um utilizador MongoDB e um utilizador ACL do Redis para a API, com privilégio mínimo. Estão na secção "Utilizadores MongoDB e Redis".
- **"Tarefa 5":** são os pedidos e respostas da tarefa 4.
- **"Tarefa 6":** é o output dos scripts de setup do MongoDB e do Redis.

## Como correr

A partir da raiz do repositório, com os motores a correr (`docker compose up -d`):

```bash
# 0. Variáveis: copiar e preencher (as palavras-passe de root/default têm de ser as do .env da raiz)
cp exercises/09-security/exercise/api/.env.example exercises/09-security/exercise/api/.env
set -a; source exercises/09-security/exercise/api/.env; set +a

# 1. Base de dados e roles (as palavras-passe vão como variáveis do psql, nunca no ficheiro)
./scripts/create-db.sh ex09 --pagila --reset
docker compose exec -T postgres psql -U postgres -d ex09 -v ON_ERROR_STOP=1 \
  -v migrations_password="$EX09_MIGRATIONS_PASSWORD" \
  -v app_password="$EX09_APP_PASSWORD" \
  -v readonly_password="$EX09_READONLY_PASSWORD" \
  < exercises/09-security/exercise/roles.sql

# 2. Provas (sem ON_ERROR_STOP: algumas instruções têm de falhar)
docker compose exec -T postgres psql -U postgres -d ex09 -e < exercises/09-security/exercise/proofs.sql

# 3. Utilizadores MongoDB e Redis, e a API
cd exercises/09-security/exercise/api
uv sync
uv run python -m scripts.setup_mongo
uv run python -m scripts.setup_redis
uv run uvicorn app.main:app --port 8009
```

Os resultados abaixo foram obtidos com a API a correr num contentor `uv` (Python 3.13) na rede do `docker compose`, publicada em `127.0.0.1:8009`.

## Tarefa 1: `roles.sql`

| Role | Privilégios |
|------|-------------|
| `ex09_migrations` | Dono da base de dados `ex09`. Único role (além do superutilizador) com `CREATE` no schema `public`. |
| `ex09_app` | `SELECT`, `INSERT`, `UPDATE`, `DELETE` em todas as tabelas e `USAGE` em todas as sequências. Não é dono de nada e não pode criar objetos. |
| `ex09_readonly` | `SELECT` em todas as tabelas |
| `PUBLIC` | Perde `CREATE` no schema `public` |

`ALTER DEFAULT PRIVILEGES FOR ROLE ex09_migrations` faz com que as tabelas e sequências criadas no futuro por `ex09_migrations` recebam os mesmos privilégios.

Uma descoberta ao testar: no Pagila, o dono do schema `public` é o `postgres` e não o `pg_database_owner`. Por isso, ser dono da base de dados não deixava o `ex09_migrations` criar tabelas (`permission denied for schema public`), e foi preciso um `GRANT CREATE ON SCHEMA public TO ex09_migrations` explícito.

## Tarefa 2: output de `proofs.sql`

```
SET ROLE ex09_app;
SET
SELECT current_user;
 current_user
--------------
 ex09_app
(1 row)

-- Esperado: FALHA
DROP TABLE film;
ERROR:  must be owner of table film

-- Esperado: FUNCIONA
INSERT INTO actor (first_name, last_name) VALUES ('X', 'Y');
INSERT 0 1

RESET ROLE;
RESET
SET ROLE ex09_readonly;
SET
SELECT current_user;
 current_user
---------------
 ex09_readonly
(1 row)

-- Esperado: FUNCIONA
SELECT count(*) FROM film;
 count
-------
  1000
(1 row)

-- Esperado: FALHA
INSERT INTO actor (first_name, last_name) VALUES ('X', 'Y');
ERROR:  permission denied for table actor
RESET ROLE;
RESET
```

As 4 provas pedidas dão o resultado esperado. Provas extra, para os privilégios por omissão e para o `REVOKE CREATE`:

```
SET ROLE ex09_migrations;
-- Esperado: FUNCIONA
CREATE TABLE ex09_probe (id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY, note text);
CREATE TABLE
RESET ROLE;

SET ROLE ex09_app;
-- Esperado: FUNCIONA, a tabela nova já tem INSERT para ex09_app (default privileges)
INSERT INTO ex09_probe (note) VALUES ('default privileges work') RETURNING id, note;
 id |          note
----+-------------------------
  1 | default privileges work
(1 row)

INSERT 0 1
-- Esperado: FALHA
CREATE TABLE ex09_should_fail (id integer);
ERROR:  permission denied for schema public
RESET ROLE;

SET ROLE ex09_readonly;
-- Esperado: FUNCIONA
SELECT id, note FROM ex09_probe;
 id |          note
----+-------------------------
  1 | default privileges work
(1 row)
```

O fim do ficheiro apaga a tabela de teste e o ator `X Y`.

## Utilizadores MongoDB e Redis

### MongoDB: `ex09_app` com `readWrite` só em `ex09`

`uv run python -m scripts.setup_mongo`:

```
created user ex09_app on ex09: readWrite on ex09
collection notes: $jsonSchema validator (customer_id int, text string)
connected as [{'user': 'ex09_app', 'db': 'ex09'}]
insert into ex09.probe: allowed
insert note with an object as text: refused by the validator (Document failed validation)
insert into ex09_other: refused (Unauthorized)
dropDatabase ex09: refused (Unauthorized)
```

O utilizador vive na base de dados `ex09` (`authSource=ex09`) e só pode ler e escrever coleções dessa base de dados. A coleção `notes` tem também um validador `$jsonSchema`: mesmo que a API deixasse passar um tipo errado, o MongoDB recusava o documento.

### Redis: `ex09_app` só pode fazer `INCR` em `counter:*`

`uv run python -m scripts.setup_redis`:

```
ACL SETUSER ex09_app reset on >*** ~counter:* resetchannels -@all +incr
ACL GETUSER ex09_app: commands=['+incr'] keys=['~counter:*']
INCR counter:setup_probe -> 1
INCRBY counter:setup_probe 5 -> User ex09_app has no permissions to run the 'incrby' command
INCR other:key               -> No permissions to access a key
GET counter:setup_probe      -> User ex09_app has no permissions to run the 'get' command
SET counter:setup_probe 1    -> User ex09_app has no permissions to run the 'set' command
DEL counter:setup_probe      -> User ex09_app has no permissions to run the 'del' command
FLUSHALL                     -> User ex09_app has no permissions to run the 'flushall' command
KEYS *                       -> User ex09_app has no permissions to run the 'keys' command
CONFIG GET maxmemory         -> User ex09_app has no permissions to run the 'config|get' command
```

O ACL é mais apertado do que o do tutorial (`+@all -@dangerous`): a API só precisa de `INCR` em chaves `counter:*`, por isso é só isso que pode fazer. Os comandos perigosos só são enviados como `ex09_app` depois de `ACL DRYRUN` confirmar que o ACL os recusa, por isso nunca correm a sério. Um detalhe que apareceu ao testar: `r.incr()` do redis-py envia `INCRBY`, que este ACL recusa. Por isso a API envia `INCR` explicitamente com `execute_command`.

### O `ACL SETUSER` perde-se quando o Redis reinicia

O `ACL SETUSER` só existe na memória do Redis. Neste `docker-compose.yml`, o Redis arranca só com `--requirepass` e sem ficheiro de ACL:

```
$ redis-cli ACL SAVE
ERR This Redis instance is not configured to use an ACL file. ...
$ redis-cli CONFIG GET aclfile
aclfile
(vazio)
```

Ao reiniciar, o utilizador `ex09_app` desaparece e a API deixa de conseguir autenticar-se. Há duas formas de o manter:
- **Ficheiro de ACL (a minha escolha):** arrancar o Redis com `--aclfile /data/users.acl`, no volume `redis_data`, e correr `ACL SAVE` depois de cada `ACL SETUSER`. Ao arrancar, o Redis lê os utilizadores desse ficheiro. Com `aclfile`, a palavra-passe do utilizador `default` também tem de ir para o ficheiro (`user default on >... ~* +@all`), em vez de `--requirepass`.
- **Script de setup no arranque:** correr o `setup_redis.py` sempre que o Redis arranca, por exemplo como passo de arranque da aplicação. Funciona, mas fica um intervalo sem o utilizador.

## Tarefa 3: a API

| Endpoint | Motor | Proteção |
|----------|-------|----------|
| `POST /actors` | PostgreSQL, role `ex09_app` | `INSERT ... VALUES (%s, %s)`: query parametrizada. Os valores vão separados do texto SQL e nunca são interpretados como SQL. |
| `POST /notes` | MongoDB, utilizador `ex09_app` | Modelo Pydantic com `strict=True` e `extra="forbid"`: `customer_id` tem de ser um inteiro JSON e `text` uma string JSON. Qualquer outro tipo ou campo dá `422`. O documento é construído campo a campo a partir do modelo validado, nunca a partir do JSON bruto. |
| `POST /counters/{name}` | Redis, utilizador ACL `ex09_app` | `Path(pattern=r"^[a-z0-9_-]{1,32}$")`: um nome fora do padrão dá `422` antes de chegar ao Redis. |

Nenhuma query é construída concatenando input do utilizador. As credenciais vêm de variáveis de ambiente (`api/.env`, que não vai para o git) e a API só conhece as credenciais de aplicação. As de administração só são usadas pelos scripts de setup.

### Pedidos normais

```
$ curl -s -i -X POST http://127.0.0.1:8009/actors -H 'Content-Type: application/json' -d '{"first_name": "ADA", "last_name": "LOVELACE"}'
HTTP/1.1 201 Created
content-type: application/json

{"actor_id":202}

$ curl -s -i -X POST http://127.0.0.1:8009/notes -H 'Content-Type: application/json' -d '{"customer_id": 1, "text": "Pediu recomendacoes de ficcao cientifica."}'
HTTP/1.1 201 Created
content-type: application/json

{"note_id":"6ae34ea51dacd00e8976437b"}

$ curl -s -i -X POST http://127.0.0.1:8009/counters/home_page
HTTP/1.1 200 OK
content-type: application/json

{"name":"home_page","value":1}

$ curl -s -i -X POST http://127.0.0.1:8009/counters/home_page
HTTP/1.1 200 OK
content-type: application/json

{"name":"home_page","value":2}
```

## Tarefa 4: provas de que a API é segura

### Injeção SQL em `POST /actors`

```
$ curl -s -i -X POST http://127.0.0.1:8009/actors -H 'Content-Type: application/json' -d '{"first_name": "x'"'"'); DROP TABLE actor; --", "last_name": "y"}'
HTTP/1.1 201 Created
content-type: application/json

{"actor_id":203}
```

O que ficou guardado:

```
$ docker compose exec -T postgres psql -U postgres -d ex09 -c "SELECT actor_id, first_name, last_name FROM actor WHERE actor_id >= 202 ORDER BY actor_id;"
 actor_id |        first_name         | last_name
----------+---------------------------+-----------
      202 | ADA                       | LOVELACE
      203 | x'); DROP TABLE actor; -- | y
(2 rows)

$ docker compose exec -T postgres psql -U postgres -d ex09 -c "SELECT to_regclass('public.actor') AS actor_table, count(*) AS actors FROM actor;"
 actor_table | actors
-------------+--------
 actor       |    202
(1 row)
```

O texto ficou guardado tal como foi enviado e a tabela `actor` continua a existir. Com a query parametrizada, o PostgreSQL recebe o texto SQL (`INSERT ... VALUES ($1, $2)`) e os valores em separado, por isso o `'); DROP TABLE` nunca é lido como SQL. Mesmo que fosse, o `ex09_app` não é dono de `actor` e o `DROP TABLE` falhava (tarefa 2).

### Injeção NoSQL em `POST /notes`

```
$ curl -s -i -X POST http://127.0.0.1:8009/notes -H 'Content-Type: application/json' -d '{"customer_id": 1, "text": {"$ne": null}}'
HTTP/1.1 422 Unprocessable Content
content-type: application/json

{"detail":[{"type":"string_type","loc":["body","text"],"msg":"Input should be a valid string","input":{"$ne":null}}]}
```

Outros tipos também dão `422`:

```
$ curl -s -i -X POST http://127.0.0.1:8009/notes -H 'Content-Type: application/json' -d '{"customer_id": "1", "text": "id como texto"}'
HTTP/1.1 422 Unprocessable Content

{"detail":[{"type":"int_type","loc":["body","customer_id"],"msg":"Input should be a valid integer","input":"1"}]}

$ curl -s -i -X POST http://127.0.0.1:8009/notes -H 'Content-Type: application/json' -d '{"customer_id": 1, "text": "campo a mais", "$where": "1"}'
HTTP/1.1 422 Unprocessable Content

{"detail":[{"type":"extra_forbidden","loc":["body","$where"],"msg":"Extra inputs are not permitted","input":"1"}]}
```

O que ficou guardado: só a nota válida.

```
$ docker compose exec -T mongo mongosh --quiet -u root -p ... --authenticationDatabase admin ex09 --eval 'printjson(db.notes.find({}, {_id: 0}).toArray())'
[
  {
    customer_id: 1,
    text: 'Pediu recomendacoes de ficcao cientifica.'
  }
]
notes: 1
```

### Nomes de contadores inválidos em `POST /counters/{name}`

```
$ curl -s -i -X POST http://127.0.0.1:8009/counters/a*
HTTP/1.1 422 Unprocessable Content
content-type: application/json

{"detail":[{"type":"string_pattern_mismatch","loc":["path","name"],"msg":"String should match pattern '^[a-z0-9_-]{1,32}$'","input":"a*","ctx":{"pattern":"^[a-z0-9_-]{1,32}$"}}]}

$ curl -s -i -X POST http://127.0.0.1:8009/counters/x:y
HTTP/1.1 422 Unprocessable Content
content-type: application/json

{"detail":[{"type":"string_pattern_mismatch","loc":["path","name"],"msg":"String should match pattern '^[a-z0-9_-]{1,32}$'","input":"x:y","ctx":{"pattern":"^[a-z0-9_-]{1,32}$"}}]}
```

O que ficou guardado no Redis: só o contador válido.

```
$ redis-cli --scan --pattern 'counter:*'
counter:home_page
$ redis-cli GET counter:home_page
2
```

O padrão impede que o nome mude a forma da chave. Com `x:y`, a chave seria `counter:x:y`, que podia colidir com outro espaço de nomes. Com `*`, o nome podia ser usado mais tarde como padrão num `SCAN`. Mesmo que o nome passasse, o ACL só deixa o `ex09_app` mexer em chaves `counter:*`.
