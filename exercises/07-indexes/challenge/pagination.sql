-- Desafio 07: paginação com OFFSET vs keyset, e Index Only Scan vs VACUUM.
-- Antes: criar big_rental com o setup.sql do exercício, numa base de dados própria:
--   ./scripts/create-db.sh ch07 --reset
--   docker compose exec -T postgres psql -U postgres -d ch07 -v ON_ERROR_STOP=1 < exercises/07-indexes/exercise/setup.sql
-- Correr:
--   docker compose exec -T postgres psql -U postgres -d ch07 -v ON_ERROR_STOP=1 -e < exercises/07-indexes/challenge/pagination.sql

-- 1. Índice com a mesma ordem da paginação.
CREATE INDEX big_rental_page ON big_rental (rented_at DESC, id DESC);

-- 2. Página 5000 com OFFSET (salta 99 980 linhas).
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, rented_at, customer_id FROM big_rental
ORDER BY rented_at DESC, id DESC OFFSET 99980 LIMIT 20;

-- 3. Página 5000 com keyset: guardar a última linha da página 4999 em variáveis do psql...
SELECT rented_at AS last_rented_at, id AS last_id
FROM big_rental ORDER BY rented_at DESC, id DESC OFFSET 99979 LIMIT 1 \gset

\echo last_rented_at = :'last_rented_at', last_id = :last_id

-- ... e continuar a partir dela.
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, rented_at, customer_id FROM big_rental
WHERE (rented_at, id) < (:'last_rented_at', :last_id)
ORDER BY rented_at DESC, id DESC LIMIT 20;

-- As duas formas devolvem as mesmas 20 linhas: a diferença simétrica está vazia.
WITH by_offset AS (
    SELECT id, rented_at, customer_id FROM big_rental
    ORDER BY rented_at DESC, id DESC OFFSET 99980 LIMIT 20
),
by_keyset AS (
    SELECT id, rented_at, customer_id FROM big_rental
    WHERE (rented_at, id) < (:'last_rented_at', :last_id)
    ORDER BY rented_at DESC, id DESC LIMIT 20
)
SELECT (SELECT count(*) FROM by_offset) AS offset_rows,
       (SELECT count(*) FROM by_keyset) AS keyset_rows,
       (SELECT count(*) FROM (SELECT * FROM by_offset EXCEPT SELECT * FROM by_keyset) d) AS only_in_offset,
       (SELECT count(*) FROM (SELECT * FROM by_keyset EXCEPT SELECT * FROM by_offset) d) AS only_in_keyset;

-- As 20 linhas (keyset), para ver o conteúdo.
SELECT id, rented_at, customer_id FROM big_rental
WHERE (rented_at, id) < (:'last_rented_at', :last_id)
ORDER BY rented_at DESC, id DESC LIMIT 20;

-- Extra: página 50 000 (salta 999 980 linhas), para mostrar que o OFFSET piora com o número
-- da página e o keyset não.
EXPLAIN (ANALYZE)
SELECT id, rented_at, customer_id FROM big_rental
ORDER BY rented_at DESC, id DESC OFFSET 999980 LIMIT 20;

SELECT rented_at AS last_rented_at, id AS last_id
FROM big_rental ORDER BY rented_at DESC, id DESC OFFSET 999979 LIMIT 1 \gset

EXPLAIN (ANALYZE)
SELECT id, rented_at, customer_id FROM big_rental
WHERE (rented_at, id) < (:'last_rented_at', :last_id)
ORDER BY rented_at DESC, id DESC LIMIT 20;

-- Voltar à página 5000 para os passos seguintes.
SELECT rented_at AS last_rented_at, id AS last_id
FROM big_rental ORDER BY rented_at DESC, id DESC OFFSET 99979 LIMIT 1 \gset

-- 4. Recriar o índice com customer_id incluído: a consulta keyset passa a ler só o índice.
DROP INDEX big_rental_page;
CREATE INDEX big_rental_page ON big_rental (rented_at DESC, id DESC) INCLUDE (customer_id);

EXPLAIN (ANALYZE, BUFFERS)
SELECT id, rented_at, customer_id FROM big_rental
WHERE (rented_at, id) < (:'last_rented_at', :last_id)
ORDER BY rented_at DESC, id DESC LIMIT 20;

-- 5. Um UPDATE que não muda nenhum valor, mas cria versões novas de 2% das linhas
--    e tira as páginas onde elas estão do "all-visible" do visibility map.
UPDATE big_rental SET customer_id = customer_id WHERE id % 50 = 0;

EXPLAIN (ANALYZE, BUFFERS)
SELECT id, rented_at, customer_id FROM big_rental
WHERE (rented_at, id) < (:'last_rented_at', :last_id)
ORDER BY rented_at DESC, id DESC LIMIT 20;

VACUUM big_rental;

EXPLAIN (ANALYZE, BUFFERS)
SELECT id, rented_at, customer_id FROM big_rental
WHERE (rented_at, id) < (:'last_rented_at', :last_id)
ORDER BY rented_at DESC, id DESC LIMIT 20;
