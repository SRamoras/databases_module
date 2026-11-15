# Desafio 12: renomear `customer.email` sem parar a API (expand e contract)

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `api_v1.py` | Versão 1 da API (porta 8001): só conhece `customer.email` |
| `api_v2.py` | Versão 2 da API (porta 8002): só conhece `customer.email_address`. O campo JSON continua a chamar-se `email` |
| `db.py` | Engine e `get_session` (uma sessão por pedido), partilhados pelas duas versões |
| `email_sync.py` | A função e o trigger que mantêm as duas colunas iguais (usados pela 0004 e pelo `downgrade` da 0005) |
| `migrations/versions/0004_expand_email_address.py` | Migração `expand` |
| `migrations/versions/0005_contract_email.py` | Migração `contract` |
| `alembic.ini`, `migrations/env.py` | Alembic. `version_locations` junta as migrações 0001 a 0003 do exercício (`../exercise/migrations/versions`) às 0004 e 0005 daqui |
| `check_versions.py` | Tarefa 3: escreve por uma versão e lê pela outra, nos dois sentidos |
| `pyproject.toml` | Projeto uv |

Os dois endpoints, iguais nas duas versões:
- `GET /customers/{customer_id}` devolve `{"version", "customer_id", "first_name", "last_name", "email"}`.
- `PUT /customers/{customer_id}/email` com `{"email": "..."}` altera o email (numa transação, com a linha bloqueada).

## Como correr

A partir da raiz do repositório, numa cópia nova do Pagila:

```bash
./scripts/create-db.sh ch12 --pagila --reset

cd exercises/12-api/challenge
uv sync
export DATABASE_URL="postgresql://postgres:<POSTGRES_PASSWORD do .env>@localhost:5432/ch12"

uv run alembic stamp 0001_baseline
uv run alembic upgrade 0003_one_open_rental_per_copy                         # o estado final do exercício
uv run uvicorn api_v1:app --port 8001 &             # a versão 1 em produção

uv run alembic upgrade 0004                         # expand
uv run uvicorn api_v2:app --port 8002 &             # a versão 2 ao lado da 1
uv run python check_versions.py                     # tarefa 3

kill %1                                             # parar a versão 1
uv run alembic upgrade 0005                         # contract
uv run python check_versions.py v2                  # só a versão 2

uv run alembic downgrade -1                         # tarefa 5: desfaz contract
uv run alembic downgrade -1                         # tarefa 5: desfaz expand
```

Os outputs abaixo foram obtidos com as APIs a correr em contentores `uv` (Python 3.13), publicados em `127.0.0.1:8001` e `127.0.0.1:8002`.

## Ordem do deployment

| # | Passo | Colunas | Versões a correr |
|---|-------|---------|------------------|
| 0 | Estado inicial (`0003_one_open_rental_per_copy`) | `email` | v1 |
| 1 | `alembic upgrade 0004` (expand): `email_address`, o trigger e o backfill | `email`, `email_address` (iguais) | v1 |
| 2 | Arrancar a v2 | `email`, `email_address` | v1 e v2 |
| 3 | Passar o tráfego para a v2 e parar a v1 (num deploy real, à medida que as instâncias são substituídas) | `email`, `email_address` | v2 |
| 4 | `alembic upgrade 0005` (contract): apagar o trigger e `email` | `email_address` | v2 |

Em nenhum momento uma versão a correr deixa de encontrar a coluna que usa:
- antes do passo 1 só a v1 corre e `email` existe;
- entre os passos 1 e 4 as duas colunas existem e o trigger mantém-nas iguais, seja qual for a versão que escreve;
- o passo 4 só é feito depois de a v1 parar.

**Porque é que o trigger é criado antes do backfill.** Se o backfill corresse primeiro, uma alteração feita pela v1 entre o backfill e a criação do trigger ficava só em `email`. Com o trigger já criado, essa alteração é copiada para `email_address`, e o backfill (que só toca nas linhas com `email_address IS DISTINCT FROM email`) trata das restantes. Toda a migração corre numa transação, por isso a v1 nunca vê `email_address` meio preenchida.

**O trigger** (`BEFORE INSERT OR UPDATE OF email, email_address`):
- num `INSERT`, preenche a coluna que vier vazia com a outra;
- num `UPDATE`, se só `email` mudou (v1), copia para `email_address`; se só `email_address` mudou (v2), copia para `email`.

Comparar com `OLD` evita um ciclo e não sobrepõe nada quando nenhuma das colunas muda.

## Output

### Passos 0 a 2: expand, com a v1 a correr

```
$ alembic stamp 0001_baseline
INFO  [alembic.runtime.migration] Running stamp_revision  -> 0001_baseline
$ alembic upgrade 0003_one_open_rental_per_copy
INFO  [alembic.runtime.migration] Running upgrade 0001_baseline -> 0002_loyalty_points, customer.loyalty_points, preenchido com o número de alugueres
INFO  [alembic.runtime.migration] Running upgrade 0002_loyalty_points -> 0003_one_open_rental_per_copy, no máximo um aluguer aberto por cópia
(api v1 running on port 8001)

$ alembic upgrade 0004
INFO  [alembic.runtime.migration] Running upgrade 0003_one_open_rental_per_copy -> 0004, expand: add customer.email_address and keep it in sync with customer.email
  column_name
---------------
 email
 email_address

       tgname
---------------------
 customer_sync_email
 last_updated

-- clientes com email diferente de email_address depois do backfill
 different
-----------
         0
(api v2 running on port 8002)
```

### Passo 3: `check_versions` depois da migração expand

```
$ uv run python check_versions.py
== written by v1 (email), read by v2 (email_address)
PUT http://127.0.0.1:8001/customers/1/email: 200 {"version":1,"customer_id":1,"first_name":"MARY","last_name":"SMITH","email":"v1-1794701983539@example.org"}
GET http://127.0.0.1:8002/customers/1: 200 {"version":2,"customer_id":1,"first_name":"MARY","last_name":"SMITH","email":"v1-1794701983539@example.org"}
  OK   http://127.0.0.1:8002 sees v1-1794701983539@example.org
== written by v2 (email_address), read by v1 (email)
PUT http://127.0.0.1:8002/customers/1/email: 200 {"version":2,"customer_id":1,"first_name":"MARY","last_name":"SMITH","email":"v2-1794701983723@example.org"}
GET http://127.0.0.1:8001/customers/1: 200 {"version":1,"customer_id":1,"first_name":"MARY","last_name":"SMITH","email":"v2-1794701983723@example.org"}
  OK   http://127.0.0.1:8001 sees v2-1794701983723@example.org
all checks passed
```

(Nas corridas, o script estava num contentor e chamava as APIs por `host.docker.internal:8001` e `:8002`. Troquei o nome do host para `127.0.0.1`, que é o que aparece ao correr no próprio computador.)

### Passo 4: contract, só com a v2

```
(api v1 stopped)
$ alembic upgrade 0005
INFO  [alembic.runtime.migration] Running upgrade 0004 -> 0005, contract: drop the sync trigger and customer.email
  column_name
---------------
 email_address

    tgname
--------------
 last_updated

$ uv run python check_versions.py v2
PUT http://127.0.0.1:8002/customers/1/email: 200 {"version":2,"customer_id":1,"first_name":"MARY","last_name":"SMITH","email":"v2-1794701989322@example.org"}
GET http://127.0.0.1:8002/customers/1: 200 {"version":2,"customer_id":1,"first_name":"MARY","last_name":"SMITH","email":"v2-1794701989322@example.org"}
  OK   http://127.0.0.1:8002 sees v2-1794701989322@example.org
all checks passed
```

`email` já não existe e a v2 continua a funcionar. Para confirmar porque é que a v1 tinha de parar antes, arranquei-a outra vez com o esquema já contraído:

```
$ curl http://127.0.0.1:8001/customers/1
Internal Server Error  -> HTTP 500
psycopg.errors.UndefinedColumn: column customer.email does not exist
```

### Tarefa 5: `downgrade` de cada migração

`downgrade` da contract: `email` volta, preenchida a partir de `email_address`, e o trigger também. A v1 pode voltar a correr ao lado da v2:

```
$ alembic downgrade -1
INFO  [alembic.runtime.migration] Running downgrade 0005 -> 0004, contract: drop the sync trigger and customer.email
$ alembic current
0004
  column_name
---------------
 email
 email_address

       tgname
---------------------
 customer_sync_email
 last_updated

(api v1 running on port 8001)
$ uv run python check_versions.py
== written by v1 (email), read by v2 (email_address)
PUT http://127.0.0.1:8001/customers/1/email: 200 {"version":1,...,"email":"v1-1794702002043@example.org"}
GET http://127.0.0.1:8002/customers/1: 200 {"version":2,...,"email":"v1-1794702002043@example.org"}
  OK   http://127.0.0.1:8002 sees v1-1794702002043@example.org
== written by v2 (email_address), read by v1 (email)
PUT http://127.0.0.1:8002/customers/1/email: 200 {"version":2,...,"email":"v2-1794702002189@example.org"}
GET http://127.0.0.1:8001/customers/1: 200 {"version":1,...,"email":"v2-1794702002189@example.org"}
  OK   http://127.0.0.1:8001 sees v2-1794702002189@example.org
all checks passed
```

`downgrade` da expand (depois de parar a v2): `email_address`, o trigger e a função desaparecem. A v1 continua a funcionar e o último email escrito pela v2 ficou em `email`:

```
(api v2 stopped)
$ alembic downgrade -1
INFO  [alembic.runtime.migration] Running downgrade 0004 -> 0003_one_open_rental_per_copy, expand: add customer.email_address and keep it in sync with customer.email
$ alembic current
0003_one_open_rental_per_copy
 column_name
-------------
 email

    tgname
--------------
 last_updated

$ curl http://127.0.0.1:8001/customers/1
{"version":1,"customer_id":1,"first_name":"MARY","last_name":"SMITH","email":"v2-1794702002189@example.org"}  -> HTTP 200
```

E outra vez até ao fim:

```
$ alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade 0003_one_open_rental_per_copy -> 0004, expand: add customer.email_address and keep it in sync with customer.email
INFO  [alembic.runtime.migration] Running upgrade 0004 -> 0005, contract: drop the sync trigger and customer.email
  column_name
---------------
 email_address
```

O `downgrade` também segue a regra do deployment ao contrário: desfazer a contract é seguro com a v2 a correr; desfazer a expand só depois de parar a v2, porque a v2 usa `email_address`.

## Porque não um `ALTER TABLE ... RENAME COLUMN`

`RENAME COLUMN` é instantâneo, mas no momento em que corre a versão que está em produção deixa de encontrar a coluna (o mesmo `UndefinedColumn` de cima). Teria de se parar a API, migrar e arrancar a versão nova ao mesmo tempo, o que é downtime, e não há maneira de ter as duas versões a correr durante um deploy gradual. Expand e contract troca uma migração por duas e um trigger temporário por zero pedidos falhados.
