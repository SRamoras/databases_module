# Desafio 07: Paginação com `OFFSET` vs keyset, e `VACUUM`

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `pagination.sql` | Todas as instruções, por ordem (tarefas 1 a 5, mais a página 50 000 como extra) |
| `README.md` | Este ficheiro |

A tabela `big_rental` é criada com o `setup.sql` do exercício (`../exercise/setup.sql`).

## Como correr

A partir da raiz do repositório:

```bash
./scripts/create-db.sh ch07 --reset
docker compose exec -T postgres psql -U postgres -d ch07 -v ON_ERROR_STOP=1 < exercises/07-indexes/exercise/setup.sql
docker compose exec -T postgres psql -U postgres -d ch07 -v ON_ERROR_STOP=1 -e < exercises/07-indexes/challenge/pagination.sql
```

O `-e` mostra cada instrução antes do seu resultado. Os valores de `rented_at` dependem do momento em que o `setup.sql` corre (usa `now()`), por isso as datas mudam de uma execução para outra.

## Tarefa 1: índice com a ordem da paginação

```sql
CREATE INDEX big_rental_page ON big_rental (rented_at DESC, id DESC);
```

`id` entra no índice e na ordenação como desempate: há linhas com o mesmo `rented_at`, e sem um desempate único a ordem entre elas não está definida. Uma linha podia então aparecer em duas páginas, ou em nenhuma.

## Tarefa 2: página 5 000 com `OFFSET`

```sql
SELECT id, rented_at, customer_id FROM big_rental
ORDER BY rented_at DESC, id DESC OFFSET 99980 LIMIT 20;
```

```
 Limit (actual time=118.097..118.106 rows=20.00 loops=1)
   Buffers: shared hit=89678 read=10699 written=1163
   ->  Index Scan using big_rental_page on big_rental (actual time=0.072..115.423 rows=100000.00 loops=1)
         Index Searches: 1
         Buffers: shared hit=89678 read=10699 written=1163
 Execution Time: 118.143 ms
```

O índice dá as linhas já pela ordem certa, mas o `Index Scan` produz **100 000 linhas** (`rows=100000`) para o `Limit` deitar fora as primeiras 99 980. Toca em ~100 000 páginas (`hit` + `read`).

## Tarefa 3: a mesma página com keyset

A última linha da página 4 999 fica guardada em variáveis do psql com `\gset`:

```
last_rented_at = '2026-09-05 16:04:59.244702+00', last_id = 13584
```

```sql
SELECT id, rented_at, customer_id FROM big_rental
WHERE (rented_at, id) < (:'last_rented_at', :last_id)
ORDER BY rented_at DESC, id DESC LIMIT 20;
```

```
 Limit (actual time=0.026..0.044 rows=20.00 loops=1)
   Buffers: shared hit=22 read=1
   ->  Index Scan using big_rental_page on big_rental (actual time=0.026..0.041 rows=20.00 loops=1)
         Index Cond: (ROW(rented_at, id) < ROW('2026-09-05 16:04:59.244702+00'::timestamp with time zone, 13584))
         Index Searches: 1
         Buffers: shared hit=22 read=1
 Execution Time: 0.073 ms
```

A comparação de linhas `(rented_at, id) < (...)` é uma condição do índice (`Index Cond`). O PostgreSQL desce a árvore diretamente até à posição da última linha vista e lê só as 20 seguintes, em 23 páginas.

**As duas formas devolvem as mesmas 20 linhas.** A diferença simétrica entre os dois resultados está vazia:

```
 offset_rows | keyset_rows | only_in_offset | only_in_keyset
-------------+-------------+----------------+----------------
          20 |          20 |              0 |              0
```

```
   id    |           rented_at           | customer_id
---------+-------------------------------+-------------
 1063464 | 2026-09-05 16:04:34.793502+00 |         184
 1427159 | 2026-09-05 16:03:57.987102+00 |          44
  461918 | 2026-09-05 16:03:34.659102+00 |         269
 ...
 1726621 | 2026-09-05 15:50:04.486302+00 |         386
 1845692 | 2026-09-05 15:49:38.393502+00 |         471
(20 rows)
```

### Comparação

| | OFFSET | Keyset |
|---|---|---|
| Página 5 000 | 118.1 ms, 100 000 linhas lidas, ~100 000 buffers | 0.073 ms, 20 linhas lidas, 23 buffers |
| Página 50 000 (extra) | 440.5 ms, 1 000 000 linhas lidas | 0.047 ms, 20 linhas lidas, 23 buffers |

Na página 50 000, o plano com `OFFSET` passa a `rows=1000000.00` e 440 ms. O keyset mantém o mesmo plano, com 20 linhas e 23 buffers. **O custo do keyset não depende do número da página.**

### Porque é que o `OFFSET` fica mais lento à medida que a página cresce

`OFFSET n` não salta diretamente para a linha `n`. O índice não sabe qual é a 99 981.ª entrada sem contar as anteriores, porque uma B-tree está organizada por valor, não por posição. Por isso o motor tem de produzir, uma a uma, todas as linhas anteriores e deitá-las fora. O trabalho é proporcional a `OFFSET + LIMIT`: a página 5 000 lê 100 000 linhas e a página 50 000 lê 1 000 000. O keyset diz ao índice *a partir de que valor* começar, e uma B-tree encontra um valor numa descida (cerca de 3 ou 4 níveis), seja qual for a página.

O keyset tem também uma vantagem de correção. Se entrarem linhas novas entre o pedido de uma página e o da seguinte, com `OFFSET` tudo desliza e há linhas repetidas ou saltadas. O keyset continua exatamente depois da última linha vista. A contrapartida é que não permite saltar para uma página arbitrária ("ir para a página 5 000") sem conhecer a última linha da página anterior: serve para "seguinte" e "scroll infinito".

## Tarefa 4: `INCLUDE (customer_id)` → Index Only Scan

```sql
DROP INDEX big_rental_page;
CREATE INDEX big_rental_page ON big_rental (rented_at DESC, id DESC) INCLUDE (customer_id);
```

```
 Limit (actual time=0.031..0.035 rows=20.00 loops=1)
   Buffers: shared hit=1 read=3
   ->  Index Only Scan using big_rental_page on big_rental (actual time=0.030..0.033 rows=20.00 loops=1)
         Index Cond: (ROW(rented_at, id) < ROW('2026-09-05 16:04:59.244702+00'::timestamp with time zone, 13584))
         Heap Fetches: 0
         Index Searches: 1
         Buffers: shared hit=1 read=3
 Execution Time: 0.048 ms
```

A consulta pede `id`, `rented_at` e `customer_id`, e agora as três estão no índice. `customer_id` vai em `INCLUDE`: é guardado nas folhas do índice, mas não faz parte da ordenação. Passa a ser um `Index Only Scan` com `Heap Fetches: 0`, e lê 4 páginas em vez de 23.

## Tarefa 5: `UPDATE`, `Heap Fetches` e `VACUUM`

```sql
UPDATE big_rental SET customer_id = customer_id WHERE id % 50 = 0;
-- UPDATE 40000
```

Keyset logo a seguir:

```
 Limit (actual time=0.029..0.191 rows=20.00 loops=1)
   Buffers: shared hit=19 read=5 dirtied=5 written=5
   ->  Index Only Scan using big_rental_page on big_rental (actual time=0.028..0.188 rows=20.00 loops=1)
         Index Cond: (ROW(rented_at, id) < ROW('2026-09-05 16:04:59.244702+00'::timestamp with time zone, 13584))
         Heap Fetches: 20
         Index Searches: 1
         Buffers: shared hit=19 read=5 dirtied=5 written=5
 Execution Time: 0.204 ms
```

Depois de `VACUUM big_rental;`:

```
 Limit (actual time=0.017..0.020 rows=20.00 loops=1)
   Buffers: shared hit=4
   ->  Index Only Scan using big_rental_page on big_rental (actual time=0.016..0.017 rows=20.00 loops=1)
         Index Cond: (ROW(rented_at, id) < ROW('2026-09-05 16:04:59.244702+00'::timestamp with time zone, 13584))
         Heap Fetches: 0
         Index Searches: 1
         Buffers: shared hit=4
 Execution Time: 0.030 ms
```

| Momento | Plano | Heap Fetches | Buffers | Tempo |
|---------|-------|--------------|---------|-------|
| Depois de criar o índice (tarefa 4) | Index Only Scan | 0 | 4 | 0.048 ms |
| Depois do `UPDATE` | Index Only Scan | **20** | 24 | 0.204 ms |
| Depois do `VACUUM` | Index Only Scan | **0** | 4 | 0.030 ms |

### O que o `VACUUM` muda no visibility map

O índice não guarda informação de visibilidade: não sabe se a versão da linha para que aponta é visível para a transação atual (pode ter sido apagada ou substituída por um `UPDATE` ainda por confirmar). Normalmente isso obriga a ir à tabela (*heap*) confirmar cada linha.

O **visibility map** guarda 1 bit "all-visible" por página da tabela. Quando está ligado, todas as linhas dessa página são visíveis para todas as transações, e o `Index Only Scan` pode confiar no índice sem ir à tabela. Só quando o bit está desligado é que faz um *heap fetch*.

- O `setup.sql` termina com `VACUUM ANALYZE`, por isso todas as páginas começam "all-visible": `Heap Fetches: 0`.
- O `UPDATE` não muda nenhum valor, mas no PostgreSQL um `UPDATE` cria sempre uma versão nova da linha e marca a antiga como morta. 40 000 linhas (1 em cada 50) estão espalhadas por praticamente todas as páginas, e cada página alterada perde o bit "all-visible". As 20 linhas da página 5 000 estão em páginas assim, por isso há `Heap Fetches: 20`: uma visita à tabela por linha.
- O `VACUUM` remove as versões mortas e, nas páginas em que todas as linhas que restam são visíveis para todos, volta a ligar o bit no visibility map. O `Index Only Scan` volta a não precisar da tabela: `Heap Fetches: 0`.

É por isso que, numa tabela muito alterada, o `Index Only Scan` só é realmente "only" se o autovacuum acompanhar o ritmo das escritas.
