# Desafio 04: 1 000 000 de alugueres reproduzíveis com `COPY`

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `seed.py` | Acrescenta 1 000 000 de linhas a `rental` com `COPY`. O nome da base de dados é o argumento. |
| `pyproject.toml`, `uv.lock` | Projeto uv (dependência: `psycopg[binary]`) |

O enunciado sugere `uv add faker`, mas não é preciso: um aluguer só tem IDs e datas, sem nomes nem moradas falsas. Os valores são gerados com `random.Random(42)`, que é reproduzível e muito mais rápido do que o Faker para 1 000 000 de linhas.

## Como correr

A partir da raiz do repositório:

```bash
./scripts/create-db.sh ch04_a --pagila --reset
./scripts/create-db.sh ch04_b --pagila --reset

cd exercises/04-crud/challenge
uv sync
export DATABASE_URL="postgresql://postgres:<POSTGRES_PASSWORD do .env>@localhost:5432/postgres"
time uv run seed.py ch04_a
time uv run seed.py ch04_b
```

O script usa o `DATABASE_URL` para o servidor, o utilizador e a palavra-passe, e substitui o nome da base de dados pelo argumento.

Checksum (correr em cada base de dados):

```bash
docker compose exec -T postgres psql -U postgres -d ch04_a -c "
SELECT count(*) AS new_rows,
       md5(string_agg(concat_ws('|', rental_id, rental_date, inventory_id, customer_id, return_date, staff_id), ',' ORDER BY rental_id)) AS checksum
FROM rental WHERE rental_id > 100000;"
```

## Como o script cumpre cada regra

| Regra | Como |
|-------|------|
| 1 000 000 de linhas com `COPY` | `cursor.copy("COPY rental (...) FROM STDIN")` com `write_row` para cada linha geradas por um *generator*, sem guardar o milhão de linhas em memória |
| `rental_id` de 100 001 a 1 100 000 | IDs explícitos no `COPY`. No fim, `setval('rental_rental_id_seq', 1100000)` para o próximo `INSERT` normal receber 1 100 001. |
| `inventory_id`, `customer_id`, `staff_id` existem | O script lê os IDs que existem nas tabelas `inventory`, `customer` e `staff` e escolhe só desses. As chaves estrangeiras de `rental` confirmam-no: se um ID não existisse, o `COPY` falhava. |
| `rental_date` entre 2022-01-01 e 2026-07-31 | Segundo aleatório entre `2022-01-01 00:00:00` e `2026-07-31 23:59:59` UTC |
| `return_date` é `NULL` ou posterior | 2% ficam `NULL`. Os restantes são `rental_date` + 1 segundo a 10 dias. |
| Índice único `(rental_date, inventory_id, customer_id)` | O script carrega as chaves já existentes num `set` e junta cada chave nova. Se uma combinação se repetir, sorteia outra. |
| Semente fixa | `random.Random(42)`. Os IDs são lidos com `ORDER BY`, por isso as listas de onde se sorteia são iguais nas duas cópias. |
| Idempotente | Antes de carregar, conta os alugueres 100 001 a 1 100 000. Se já lá estão todos, termina sem escrever nada. O `COPY` e o `setval` correm na mesma transação, por isso nunca fica uma carga a meio: ou entram as 1 000 000 linhas ou nenhuma. Se encontrar uma carga parcial (só possível com alterações manuais), para com erro em vez de duplicar. |

## Tempos

```
== seed ch04_a
ch04_a: 1000000 alugueres inseridos em 20.6s

real	0m21.488s
== seed ch04_b
ch04_b: 1000000 alugueres inseridos em 22.2s

real	0m22.650s
```

| Base de dados | Tempo |
|---------------|-------|
| `ch04_a` | 21.5 s |
| `ch04_b` | 22.7 s |

As duas cargas ficam abaixo dos 30 segundos. Medido com o Docker Desktop no Windows: o script correu num contentor `uv` (Python 3.13) na mesma rede Docker que o PostgreSQL.

## Checksums

```
== checksum ch04_a
 new_rows |             checksum
----------+----------------------------------
  1000000 | c9660f1f005f2cda2f5ad5f7b1b92565
(1 row)

== checksum ch04_b
 new_rows |             checksum
----------+----------------------------------
  1000000 | c9660f1f005f2cda2f5ad5f7b1b92565
(1 row)
```

Os dois checksums são iguais: as duas bases de dados têm exatamente as mesmas 1 000 000 de linhas novas.

## Prova de idempotência

Segunda execução em `ch04_a`, com a contagem e o checksum antes e depois:

```
== antes: ch04_a
 new_rows |             checksum
----------+----------------------------------
  1000000 | c9660f1f005f2cda2f5ad5f7b1b92565

== segunda execução
ch04_a: os 1000000 alugueres já existem, nada a fazer.

real	0m0.906s

== depois: ch04_a
 new_rows |             checksum
----------+----------------------------------
  1000000 | c9660f1f005f2cda2f5ad5f7b1b92565
```

A contagem e o checksum não mudaram.

## Validação das linhas novas

```sql
SELECT count(*) FILTER (WHERE rental_date < '2022-01-01' OR rental_date > '2026-07-31 23:59:59+00') AS bad_rental_date,
       count(*) FILTER (WHERE return_date IS NOT NULL AND return_date <= rental_date)           AS bad_return_date,
       count(*) FILTER (WHERE return_date IS NULL)                                             AS not_returned,
       min(rental_id), max(rental_id)
FROM rental WHERE rental_id > 100000;
```

```
 bad_rental_date | bad_return_date | not_returned |  min   |   max
-----------------+-----------------+--------------+--------+---------
               0 |               0 |        19945 | 100001 | 1100000
(1 row)

 last_value
------------
    1100000
(1 row)
```

Não há datas fora do intervalo nem devoluções anteriores ao aluguer, os IDs vão de 100 001 a 1 100 000 e a sequência ficou em 1 100 000. O índice único e as chaves estrangeiras são verificados pelo próprio PostgreSQL durante o `COPY`, que teria falhado se alguma linha os violasse.
