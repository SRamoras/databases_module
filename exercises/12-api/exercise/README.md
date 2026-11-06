# Exercício 12: Migrações reversíveis e uma API transacional

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `app/models.py` | Modelos de `customer`, `film`, `inventory`, `rental` e `staff` (só as colunas que a API usa) |
| `app/db.py` | Engine, `sessionmaker` e a dependência `get_session` (uma sessão por pedido) |
| `app/main.py` | Os 3 endpoints |
| `alembic.ini`, `migrations/env.py` | Configuração do Alembic: URL lido de `DATABASE_URL`, `target_metadata` e `include_object` |
| `migrations/versions/0001_baseline.py` | Tarefa 1: baseline vazia |
| `migrations/versions/0002_loyalty_points.py` | Tarefa 2 |
| `migrations/versions/0003_one_open_rental_per_copy.py` | Tarefa 3 |
| `migrations_roundtrip.sh` | Tarefa 4: `upgrade head`, `downgrade base`, `upgrade head`, com `\d customer` e `\d rental` depois de cada passo |
| `concurrency_test.py` | Tarefa 6 |
| `pyproject.toml`, `uv.lock` | Projeto uv |

## Como correr

A partir da raiz do repositório, com os motores a correr (`docker compose up -d`):

```bash
./scripts/create-db.sh ex12 --pagila --reset
cd exercises/12-api/exercise
uv sync
export DATABASE_URL="postgresql+psycopg://postgres:<password>@localhost:5432/ex12"

# Migrações
uv run alembic stamp 0001_baseline   # só na primeira vez: a BD já tem o esquema da baseline
uv run alembic upgrade head
./migrations_roundtrip.sh            # tarefa 4

# API (SQL_ECHO=1 liga o echo=True do engine)
SQL_ECHO=1 uv run uvicorn app.main:app --port 8000

# Noutro terminal, com a API a correr
uv run python concurrency_test.py
```

Quando a baseline era a única migração, o comando foi `alembic stamp head`. Com as três migrações escritas, `stamp head` marcaria a BD como já estando na `0003` sem correr nada, por isso agora o comando é `stamp 0001_baseline`.

## Tarefa 1: baseline e `include_object`

`0001_baseline` tem `upgrade` e `downgrade` vazios: o esquema já existe porque a BD é uma cópia da Pagila. `alembic stamp` só escreve a versão na tabela `alembic_version`, sem correr nada.

Em `migrations/env.py`:

```python
def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table":
        return name in target_metadata.tables
    # Objetos que só existem na base de dados (compare_to is None) ficam como estão.
    if reflected and compare_to is None:
        return False
    return True
```

Também tive de pôr nas FKs dos modelos `onupdate="CASCADE", ondelete="RESTRICT"`, iguais às da Pagila. Sem isso, o autogenerate via as FKs dos modelos como diferentes das da BD e propunha criá-las outra vez. Com tudo configurado, `alembic check` depois de `upgrade head` dá `No new upgrade operations detected.`

### O que o `--autogenerate` teria gerado

Testei os dois casos numa cópia do projeto, fora do repositório:

**Sem `include_object`** (contra `ex12`): 197 operações, quase todas destrutivas.

| Operação | Quantas |
|----------|---------|
| `drop_table` (todas as tabelas não mapeadas: `actor`, `address`, `payment_p2022_01`, ...) | 65 |
| `drop_index` | 91 |
| `drop_constraint` (FKs) | 11 |
| `drop_column` (colunas não mapeadas, como `customer.activebool`, `customer.uuid`, `customer.address_id`) | 24 |
| `add_column` / `create_index` / `create_foreign_key` | 1 / 1 / 4 |

**Sem baseline** (a primeira migração gerada a partir dos modelos, por exemplo contra uma BD vazia): `create_table` para `customer`, `film`, `staff`, `inventory` e `rental`, e o índice novo. Aplicada a `ex12` falha logo com `relation "customer" already exists`, porque as tabelas já existem. E se fosse gerada contra `ex12` sem nada em `alembic_version`, ficava com as alterações de hoje mas sem nenhum ponto de partida: numa BD nova o `upgrade head` não conseguiria construir o esquema.

**Porque é perigoso.** Uma migração com `drop_table` corre sem pedir confirmação, e uma tabela apagada só volta de um backup. Quem aplicasse a migração gerada sem a ler apagava 65 tabelas (pagamentos, moradas, atores) e os dados delas, numa operação que não tem `downgrade` capaz de os recuperar: o `downgrade` gerado recria tabelas vazias. Por isso: baseline + `stamp`, `include_object`, e ler sempre o ficheiro gerado antes de o aplicar.

## Tarefa 2: `0002_loyalty_points`

```python
op.add_column("customer", sa.Column("loyalty_points", sa.Integer(), nullable=True, server_default=sa.text("0")))
op.execute("UPDATE customer c SET loyalty_points = (SELECT count(*) FROM rental r WHERE r.customer_id = c.customer_id)")
op.alter_column("customer", "loyalty_points", nullable=False)
```

O `server_default` 0 fica na coluna, para os clientes novos. `downgrade` faz `drop_column`. O cliente 1 fica com 66 pontos.

## Tarefa 3: `0003_one_open_rental_per_copy`

Antes da migração:

```text
 rental_id | inventory_id |          rental_date          | return_date
-----------+--------------+-------------------------------+-------------
     12130 |         1358 | 2022-02-14 15:16:03+00        |
     87353 |         1358 | 2026-07-20 13:33:38.674648+00 |
     12792 |         1435 | 2022-02-14 15:16:03+00        |
     87318 |         1435 | 2026-07-19 12:44:26.675207+00 |
     13295 |         2408 | 2022-02-14 15:16:03+00        |
     87514 |         2408 | 2026-07-27 16:12:39.377683+00 |
```

O `upgrade` fecha o mais antigo de cada cópia com o `rental_date` do seguinte (`lead()` por `inventory_id`) e depois cria o índice:

```text
 rental_id | inventory_id |          rental_date          |          return_date
-----------+--------------+-------------------------------+-------------------------------
     12130 |         1358 | 2022-02-14 15:16:03+00        | 2026-07-20 13:33:38.674648+00
     87353 |         1358 | 2026-07-20 13:33:38.674648+00 |
     12792 |         1435 | 2022-02-14 15:16:03+00        | 2026-07-19 12:44:26.675207+00
     87318 |         1435 | 2026-07-19 12:44:26.675207+00 |
     13295 |         2408 | 2022-02-14 15:16:03+00        | 2026-07-27 16:12:39.377683+00
     87514 |         2408 | 2026-07-27 16:12:39.377683+00 |
```

```sql
CREATE UNIQUE INDEX rental_one_open_per_copy ON rental (inventory_id) WHERE return_date IS NULL;
```

### Porque é que a correção dos dados não é desfeita

- **Não há nada certo para onde voltar.** Os dados antigos eram impossíveis (a mesma cópia em dois alugueres ao mesmo tempo). O `downgrade` serve para voltar a um esquema anterior, não para voltar a pôr dados errados.
- **O `downgrade` não sabe o que mudou.** Depois do `upgrade` a aplicação continua a escrever: um destes alugueres pode ter sido devolvido entretanto. Pôr `return_date = NULL` "nos três alugueres corrigidos" podia apagar uma devolução verdadeira. Para o fazer bem teria de guardar numa tabela à parte quais as linhas mudadas e os valores antigos.
- **Não há perigo em mantê-la.** O esquema da `0002` aceita os dados corrigidos, por isso o `downgrade` só precisa de largar o índice. Correr `upgrade` outra vez também funciona: o `UPDATE` já não encontra nenhuma cópia com dois alugueres abertos e não faz nada.

## Tarefa 4: upgrade, downgrade, upgrade

Output de `./migrations_roundtrip.sh` (as linhas `Context impl` e `Will assume transactional DDL` foram removidas, e de `\d` ficam só as partes que mudam):

```text
################ alembic upgrade head ################
INFO  [alembic.runtime.migration] Running upgrade 0001_baseline -> 0002_loyalty_points, customer.loyalty_points, preenchido com o número de alugueres
INFO  [alembic.runtime.migration] Running upgrade 0002_loyalty_points -> 0003_one_open_rental_per_copy, no máximo um aluguer aberto por cópia
0003_one_open_rental_per_copy (head)
                                             Table "public.customer"
     Column     |           Type           | Collation | Nullable |                    Default
----------------+--------------------------+-----------+----------+-----------------------------------------------
 customer_id    | integer                  |           | not null | nextval('customer_customer_id_seq'::regclass)
 store_id       | integer                  |           | not null |
 first_name     | text                     |           | not null |
 last_name      | text                     |           | not null |
 email          | text                     |           |          |
 address_id     | integer                  |           | not null |
 activebool     | boolean                  |           | not null | true
 create_date    | date                     |           | not null | CURRENT_DATE
 last_update    | timestamp with time zone |           |          | now()
 active         | integer                  |           |          |
 uuid           | uuid                     |           | not null | uuidv7()
 loyalty_points | integer                  |           | not null | 0
 ...
                                           Table "public.rental"
 ...
Indexes:
    "rental_pkey" PRIMARY KEY, btree (rental_id)
    "idx_fk_inventory_id" btree (inventory_id)
    "idx_unq_rental_rental_date_inventory_id_customer_id" UNIQUE, btree (rental_date, inventory_id, customer_id)
    "rental_one_open_per_copy" UNIQUE, btree (inventory_id) WHERE return_date IS NULL
    "rental_uuid_key" UNIQUE, btree (uuid)
 ...
 customer_id | loyalty_points
-------------+----------------
           1 |             66

################ alembic downgrade base ################
INFO  [alembic.runtime.migration] Running downgrade 0003_one_open_rental_per_copy -> 0002_loyalty_points, no máximo um aluguer aberto por cópia
INFO  [alembic.runtime.migration] Running downgrade 0002_loyalty_points -> 0001_baseline, customer.loyalty_points, preenchido com o número de alugueres
INFO  [alembic.runtime.migration] Running downgrade 0001_baseline -> , baseline: o esquema da Pagila tal como já existe
                                             Table "public.customer"
 ...
 active      | integer                  |           |          |
 uuid        | uuid                     |           | not null | uuidv7()
Indexes:                                              <- sem loyalty_points
 ...
                                           Table "public.rental"
 ...
Indexes:
    "rental_pkey" PRIMARY KEY, btree (rental_id)
    "idx_fk_inventory_id" btree (inventory_id)
    "idx_unq_rental_rental_date_inventory_id_customer_id" UNIQUE, btree (rental_date, inventory_id, customer_id)
    "rental_uuid_key" UNIQUE, btree (uuid)            <- sem rental_one_open_per_copy
 ...
ERROR:  column "loyalty_points" does not exist

################ alembic upgrade head ################
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_baseline, baseline: o esquema da Pagila tal como já existe
INFO  [alembic.runtime.migration] Running upgrade 0001_baseline -> 0002_loyalty_points, customer.loyalty_points, preenchido com o número de alugueres
INFO  [alembic.runtime.migration] Running upgrade 0002_loyalty_points -> 0003_one_open_rental_per_copy, no máximo um aluguer aberto por cópia
0003_one_open_rental_per_copy (head)
 ... (igual ao primeiro upgrade: loyalty_points not null default 0, rental_one_open_per_copy, cliente 1 com 66)
```

O script termina com código 0. O `ERROR` depois do `downgrade base` vem da consulta de verificação ao `loyalty_points`, que já não existe; é o resultado esperado.

## Tarefa 5: a API

| Endpoint | Comportamento |
|----------|---------------|
| `POST /rentals` | Numa transação: 404 se o cliente ou o filme não existem; procura uma cópia do filme na loja sem aluguer aberto (`NOT EXISTS`), tranca-a com `with_for_update(skip_locked=True)`, insere o aluguer com `rental_date = now()`. `201` com `rental_id` e `inventory_id`; `409` se não há cópia livre. Se o `INSERT` violar `rental_one_open_per_copy`, repete a transação inteira, no máximo 3 vezes, e depois `409`. |
| `POST /rentals/{rental_id}/return` | Tranca o aluguer (`FOR UPDATE`) e põe `return_date = now()`. `200`; `404` se não existe; `409` se já tinha sido devolvido. |
| `GET /rentals/overdue?as_of=2026-07-31` | Alugueres abertos com `rental_date + rental_duration dias < as_of`, por `rental_date`. |

Pedidos de teste (numa cópia nova, depois das migrações):

```text
POST /rentals {"customer_id":9999,...}            -> 404 {"detail":"Customer not found"}
POST /rentals {"film_id":99999,...}               -> 404 {"detail":"Film not found"}
POST /rentals {"customer_id":1,"film_id":1,...}   -> 201 {"rental_id":87582,"inventory_id":1}
POST /rentals/87582/return                        -> 200 {"rental_id":87582,"return_date":"2026-11-06T03:08:40.215697Z"}
POST /rentals/87582/return                        -> 409 {"detail":"Rental already returned"}
POST /rentals/99999999/return                     -> 404 {"detail":"Rental not found"}
GET  /rentals/overdue?as_of=2026-07-31            -> 200, 229 itens
```

Primeiros itens de `GET /rentals/overdue?as_of=2026-07-31`:

```json
[
  {
    "rental_id": 11496,
    "rental_date": "2022-02-14T15:16:03Z",
    "due_date": "2022-02-19T15:16:03Z",
    "customer": {"customer_id": 155, "first_name": "GAIL", "last_name": "KNIGHT"},
    "film": {"film_id": 445, "title": "HYDE DOCTOR"}
  },
  {
    "rental_id": 11541,
    "rental_date": "2022-02-14T15:16:03Z",
    "due_date": "2022-02-20T15:16:03Z",
    "customer": {"customer_id": 335, "first_name": "GREGORY", "last_name": "MAULDIN"},
    "film": {"film_id": 440, "title": "HUNGER ROOF"}
  }
]
```

### Instruções SQL de `GET /rentals/overdue`

**1 `SELECT`** (mais `BEGIN (implicit)` e `ROLLBACK`), seja qual for o número de itens. Do log com `SQL_ECHO=1`:

```text
INFO sqlalchemy.engine.Engine BEGIN (implicit)
INFO sqlalchemy.engine.Engine SELECT customer.customer_id, ..., film.film_id, film.title, ..., inventory.inventory_id, ...,
       rental.rental_id, rental.rental_date, ..., rental.rental_date + interval '1 day' * film.rental_duration AS due_date
FROM rental JOIN customer ON customer.customer_id = rental.customer_id
     JOIN inventory ON inventory.inventory_id = rental.inventory_id
     JOIN film ON film.film_id = inventory.film_id
WHERE rental.return_date IS NULL AND rental.rental_date + interval '1 day' * film.rental_duration < %(param_1)s::DATE
ORDER BY rental.rental_date, rental.rental_id
INFO sqlalchemy.engine.Engine ROLLBACK
```

Os `JOIN` já são precisos para filtrar pela data de devolução, por isso usei `contains_eager`: diz ao ORM para preencher `rental.customer` e `rental.inventory.film` com as colunas que vêm nesses `JOIN`. Sem isto, cada `rental.customer` e cada `rental.inventory.film` faria uma consulta (até 1 + 2 × 229).

## Tarefa 6: concorrência

`concurrency_test.py` lança 5 threads que esperam numa `threading.Barrier` e fazem `POST /rentals` ao mesmo tempo (filme 7, loja 1, clientes 1 a 5, staff 6). No fim devolve os alugueres criados, para o teste poder correr outra vez sem recriar a BD (`--keep` deixa-os abertos).

Primeira corrida numa cópia nova:

```text
customer 1: 201 {'rental_id': 87561, 'inventory_id': 33}
customer 2: 409 {'detail': 'No copy available'}
customer 3: 409 {'detail': 'No copy available'}
customer 4: 201 {'rental_id': 87560, 'inventory_id': 32}
customer 5: 409 {'detail': 'No copy available'}

201: 2  409: 3  inventory_id: [32, 33]
OK
(devolvidos os alugueres [87560, 87561])
```

Corri-o mais 10 vezes seguidas: deu `OK` nas 10.

**Porque funciona.** O primeiro pedido tranca a cópia 32. Um segundo pedido que chegue ao mesmo tempo salta a 32 (`SKIP LOCKED`) e tranca a 33. Os outros três encontram as duas trancadas, ou já alugadas, e recebem `409`. Sem `skip_locked`, os pedidos ficavam em fila à espera da 32 e depois tentavam alugá-la outra vez.

**A nova tentativa.** Pode acontecer um pedido ler a lista de cópias livres antes de outro fazer commit, e chegar à cópia já depois de o outro largar a tranca. Nesse caso tranca uma cópia que já tem um aluguer aberto, e é o índice `rental_one_open_per_copy` que impede o segundo aluguer: o `INSERT` falha, a transação é desfeita e repete-se, agora já a ver o aluguer do outro. Nas 11 corridas não aconteceu nenhuma vez (o log não tem nenhuma violação do índice), porque o `SKIP LOCKED` evita quase todos estes casos. O código fica lá para os casos raros, e mesmo sem ele o índice garantia que nunca há dois alugueres abertos da mesma cópia.
