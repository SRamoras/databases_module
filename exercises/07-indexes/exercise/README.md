# Exercício 07: Planos de execução e índices

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `setup.sql` | Cria `big_rental` com 2 000 000 de linhas, sem índices (igual ao enunciado) |
| `indexes.sql` | Os 3 `CREATE INDEX` mantidos depois de medir |
| `README.md` | Este ficheiro |

## Como correr

A partir da raiz do repositório:

```bash
./scripts/create-db.sh ex07 --reset
docker compose exec -T postgres psql -U postgres -d ex07 -v ON_ERROR_STOP=1 < exercises/07-indexes/exercise/setup.sql
# EXPLAIN (ANALYZE, BUFFERS) de cada consulta, 3 vezes
docker compose exec -T postgres psql -U postgres -d ex07 -v ON_ERROR_STOP=1 < exercises/07-indexes/exercise/indexes.sql
# EXPLAIN (ANALYZE, BUFFERS) de cada consulta, 3 vezes
```

Cada consulta correu 3 vezes com `EXPLAIN (ANALYZE, BUFFERS)` e o tempo indicado é a mediana do `Execution Time`. Os planos abaixo são excertos (o nó principal, o filtro ou a condição do índice, e as linhas removidas). Medido no PostgreSQL 18 do `docker compose`, com o Docker Desktop no Windows.

## Resumo

| Consulta | Nó antes | Índice | Nó depois | Mediana antes | Mediana depois |
|----------|----------|--------|-----------|---------------|----------------|
| Q1 | Parallel Seq Scan | `(customer_id) WHERE returned_at IS NULL` | Index Only Scan | 31.8 ms | 0.027 ms |
| Q2 | Parallel Seq Scan + Sort | `(rented_at)` | Bitmap Heap Scan | 77.3 ms | 3.1 ms |
| Q3 | Parallel Seq Scan | nenhum serve para a consulta como está escrita | Parallel Seq Scan | 73.9 ms | 76.4 ms |
| Q3 reescrita | Parallel Seq Scan | `(rented_at)` (o mesmo da Q2) | Bitmap Heap Scan | 55.2 ms | 1.6 ms |
| Q4 | Parallel Seq Scan + HashAggregate | nenhum mantido | Parallel Seq Scan | 111.9 ms | 126.3 ms (sem índice novo) |
| Q5 | Parallel Seq Scan + Sort | `(customer_id, rented_at)` | Bitmap Heap Scan | 42.0 ms | 0.41 ms |

Tempos das 3 execuções (ms):

| Consulta | Antes | Depois |
|----------|-------|--------|
| Q1 | 33.089, 31.824, 30.413 | 0.176, 0.027, 0.023 |
| Q2 | 91.868, 77.292, 76.352 | 7.384, 3.125, 2.471 |
| Q3 | 73.914, 73.022, 77.542 | 76.358, 75.733, 84.009 |
| Q3 reescrita | 58.516, 55.246, 51.607 | 3.356, 1.606, 1.415 |
| Q4 | 111.850, 109.324, 114.183 | 114.126, 143.482, 126.257 |
| Q5 | 41.996, 39.866, 44.853 | 1.319, 0.355, 0.408 |

A primeira execução depois de criar os índices é sempre a mais lenta, porque as páginas do índice ainda não estão em memória (`read=` em vez de `hit=` nos `Buffers`). Por isso se usa a mediana.

---

## Q1

```sql
SELECT count(*) FROM big_rental WHERE customer_id = 42 AND returned_at IS NULL;
```

**O que faz.** Conta quantos alugueres do cliente 42 ainda não foram devolvidos. Devolve um único número (93).

**Antes** (31.8 ms):

```
 Finalize Aggregate (actual time=30.911..33.030 rows=1.00 loops=1)
   ->  Gather
         ->  Partial Aggregate
               ->  Parallel Seq Scan on big_rental (actual time=1.198..28.660 rows=31.00 loops=3)
                     Filter: ((returned_at IS NULL) AND (customer_id = 42))
                     Rows Removed by Filter: 666636
                     Buffers: shared hit=2304 read=10432
```

**Índice:**

```sql
CREATE INDEX big_rental_open_customer ON big_rental (customer_id) WHERE returned_at IS NULL;
```

**Depois** (0.027 ms):

```
 Aggregate (actual time=0.048..0.048 rows=1.00 loops=1)
   ->  Index Only Scan using big_rental_open_customer on big_rental (actual time=0.037..0.042 rows=93.00 loops=1)
         Index Cond: (customer_id = 42)
         Heap Fetches: 0
         Buffers: shared hit=1 read=2
```

**Porquê.** Antes, a consulta lia as 12 736 páginas da tabela para encontrar 93 linhas. O índice parcial só tem as ~60 000 linhas com `returned_at IS NULL` (3%) e ocupa 432 kB. Como a contagem só precisa de `customer_id`, que está no índice, é um `Index Only Scan`: lê 3 páginas e nunca vai à tabela (`Heap Fetches: 0`).

## Q2

```sql
SELECT * FROM big_rental WHERE rented_at >= now() - interval '1 day' ORDER BY rented_at;
```

**O que faz.** Lista todos os alugueres das últimas 24 horas (cerca de 1 900), do mais antigo para o mais recente.

**Antes** (77.3 ms):

```
 Gather Merge (actual time=87.041..89.063 rows=1880.00 loops=1)
   ->  Sort
         Sort Key: rented_at
         ->  Parallel Seq Scan on big_rental (actual time=0.466..83.464 rows=626.67 loops=3)
               Filter: (rented_at >= (now() - '1 day'::interval))
               Rows Removed by Filter: 666040
```

**Índice:**

```sql
CREATE INDEX big_rental_rented_at ON big_rental (rented_at);
```

**Depois** (3.1 ms):

```
 Sort (actual time=7.229..7.295 rows=1880.00 loops=1)
   Sort Key: rented_at
   ->  Bitmap Heap Scan on big_rental (actual time=1.134..6.562 rows=1880.00 loops=1)
         Recheck Cond: (rented_at >= (now() - '1 day'::interval))
         Heap Blocks: exact=1741
         ->  Bitmap Index Scan on big_rental_rented_at (actual time=0.914..0.914 rows=1880.00 loops=1)
               Index Cond: (rented_at >= (now() - '1 day'::interval))
```

**Porquê.** O índice encontra diretamente o intervalo de datas, em vez de ler 2 milhões de linhas. As 1 880 linhas estão espalhadas por 1 741 páginas (os IDs não seguem a ordem das datas), por isso o planeador prefere um `Bitmap Heap Scan`: junta as páginas a ler e lê cada uma uma vez, por ordem física. Depois ordena as 1 880 linhas em memória, o que é barato.

## Q3

```sql
SELECT * FROM big_rental WHERE rented_at::date = current_date - 10;
```

**O que faz.** Lista os alugueres feitos há exatamente 10 dias (o dia inteiro, cerca de 1 900 linhas).

**Antes** (73.9 ms):

```
 Gather (actual time=0.429..73.823 rows=1873.00 loops=1)
   ->  Parallel Seq Scan on big_rental (actual time=0.224..68.601 rows=624.33 loops=3)
         Filter: ((rented_at)::date = (CURRENT_DATE - 10))
         Rows Removed by Filter: 666042
```

**Índice:** nenhum serve para a consulta como está escrita.

**Depois**, com o índice `big_rental_rented_at` já criado (76.4 ms):

```
 Gather (actual time=1.965..76.276 rows=1873.00 loops=1)
   ->  Parallel Seq Scan on big_rental (actual time=0.209..69.283 rows=624.33 loops=3)
         Filter: ((rented_at)::date = (CURRENT_DATE - 10))
         Rows Removed by Filter: 666042
```

**Porque é que o índice não ajuda.** O índice está ordenado por `rented_at`, mas a condição é sobre `rented_at::date`, que é uma expressão calculada a partir da coluna. O PostgreSQL não consegue usar um índice da coluna para uma condição sobre uma função da coluna, por isso continua a calcular a expressão para os 2 milhões de linhas.

Também não se pode criar um índice sobre a expressão:

```
CREATE INDEX ON big_rental ((rented_at::date));
ERROR:  functions in index expression must be marked IMMUTABLE
```

A conversão de `timestamptz` para `date` depende do fuso horário da sessão (o mesmo instante pode ser dia 18 em Lisboa e dia 19 em Tóquio), por isso não é `IMMUTABLE`.

**Reescrita.** "O dia X inteiro" é o mesmo que o intervalo semiaberto `[X, X + 1)`, com a condição diretamente sobre a coluna:

```sql
SELECT * FROM big_rental WHERE rented_at >= current_date - 10 AND rented_at < current_date - 9;
```

Devolve as mesmas 1 873 linhas. Antes do índice: 55.2 ms, Parallel Seq Scan. Com o índice `big_rental_rented_at` (1.6 ms):

```
 Bitmap Heap Scan on big_rental (actual time=0.474..3.284 rows=1873.00 loops=1)
   Recheck Cond: ((rented_at >= (CURRENT_DATE - 10)) AND (rented_at < (CURRENT_DATE - 9)))
   Heap Blocks: exact=1750
   ->  Bitmap Index Scan on big_rental_rented_at (actual time=0.343..0.343 rows=1873.00 loops=1)
         Index Cond: ((rented_at >= (CURRENT_DATE - 10)) AND (rented_at < (CURRENT_DATE - 9)))
```

## Q4

```sql
SELECT customer_id, count(*) FROM big_rental WHERE returned_at IS NOT NULL GROUP BY customer_id;
```

**O que faz.** Para cada um dos 600 clientes, conta quantos alugueres já foram devolvidos. Devolve 600 linhas.

**Antes** (111.9 ms):

```
 Finalize GroupAggregate (actual time=109.465..111.793 rows=600.00 loops=1)
   ->  Gather Merge
         ->  Sort
               ->  Partial HashAggregate (actual time=107.436..107.474 rows=600.00 loops=3)
                     ->  Parallel Seq Scan on big_rental (actual time=0.113..43.799 rows=646640.00 loops=3)
                           Filter: (returned_at IS NOT NULL)
                           Rows Removed by Filter: 20027
```

**Índice:** nenhum mantido.

**Depois**, com os outros 3 índices criados, o plano é o mesmo (126.3 ms):

```
 Finalize GroupAggregate (actual time=110.096..114.078 rows=600.00 loops=1)
   ...
                     ->  Parallel Seq Scan on big_rental (actual time=0.063..43.435 rows=646640.00 loops=3)
                           Filter: (returned_at IS NOT NULL)
                           Rows Removed by Filter: 20027
```

**Porque é que um índice não ajuda.** A consulta precisa de 97% da tabela (1 940 000 de 2 000 000 linhas). Um índice serve para encontrar poucas linhas sem ler o resto. Aqui é preciso ler quase tudo, e a leitura sequencial da tabela inteira, em paralelo, é a forma mais barata de o fazer.

Experimentei o índice mais favorável possível, que permite um Index Only Scan:

```sql
CREATE INDEX big_rental_returned_customer ON big_rental (customer_id) WHERE returned_at IS NOT NULL;
```

Mesmo com ele, o planeador manteve o `Parallel Seq Scan` (107.9 ms e 120.7 ms). Forçando o índice com `SET enable_seqscan = off`:

```
 Finalize GroupAggregate (actual time=66.036..99.306 rows=600.00 loops=1)
   ->  Gather Merge
         ->  Partial GroupAggregate
               ->  Parallel Index Only Scan using big_rental_returned_customer on big_rental (actual time=0.160..31.954 rows=646640.00 loops=3)
                     Heap Fetches: 0
```

Mediana de 99.4 ms (99.417, 96.346, 101.236). O ganho é de cerca de 10%, porque continua a ser preciso ler e agregar 1,94 milhões de entradas. Em troca, o índice tem quase o tamanho da coluna e torna mais lenta cada escrita na tabela. Não compensa, por isso não fica em `indexes.sql`. Para esta consulta ser realmente rápida seria preciso não a recalcular a cada pedido: guardá-la numa vista materializada (sessão 06) ou manter um contador por cliente.

## Q5

```sql
SELECT * FROM big_rental
WHERE customer_id IN (7, 42, 99) AND rented_at >= now() - interval '30 days'
ORDER BY rented_at DESC;
```

**O que faz.** Lista os alugueres dos últimos 30 dias de três clientes (7, 42 e 99), do mais recente para o mais antigo. Devolve cerca de 300 linhas.

**Antes** (42.0 ms):

```
 Gather Merge (actual time=39.728..41.976 rows=295.00 loops=1)
   ->  Sort
         Sort Key: rented_at DESC
         ->  Parallel Seq Scan on big_rental (actual time=0.639..37.812 rows=98.33 loops=3)
               Filter: ((customer_id = ANY ('{7,42,99}'::integer[])) AND (rented_at >= (now() - '30 days'::interval)))
               Rows Removed by Filter: 666568
```

**Índice:**

```sql
CREATE INDEX big_rental_customer_rented_at ON big_rental (customer_id, rented_at);
```

**Depois** (0.41 ms):

```
 Sort (actual time=1.289..1.300 rows=295.00 loops=1)
   Sort Key: rented_at DESC
   ->  Bitmap Heap Scan on big_rental (actual time=0.164..1.255 rows=295.00 loops=1)
         Recheck Cond: ((customer_id = ANY ('{7,42,99}'::integer[])) AND (rented_at >= (now() - '30 days'::interval)))
         Heap Blocks: exact=290
         ->  Bitmap Index Scan on big_rental_customer_rented_at (actual time=0.122..0.123 rows=295.00 loops=1)
               Index Cond: ((customer_id = ANY ('{7,42,99}'::integer[])) AND (rented_at >= (now() - '30 days'::interval)))
               Index Searches: 3
```

**Porquê.** A ordem das colunas importa: primeiro a coluna da igualdade (`customer_id`), depois a do intervalo (`rented_at`). Assim, para cada cliente as entradas estão juntas e ordenadas por data, e o índice faz 3 pesquisas (`Index Searches: 3`), uma por cliente, cada uma a ler só os últimos 30 dias. Com a ordem inversa `(rented_at, customer_id)`, teria de percorrer os 30 dias de todos os clientes. Um índice só em `rented_at` também ajudava, mas lia ~55 000 entradas para ficar com 295.

---

## Custo das escritas

```sql
INSERT INTO big_rental SELECT g, 1, now(), NULL FROM generate_series(2000001, 2100000) g;
```

A tabela foi recriada com `setup.sql` antes de cada execução, e nos casos "com índices" foi corrido `indexes.sql` a seguir. Tempo com `\timing`:

| | Execução 1 | Execução 2 | Execução 3 | Mediana |
|---|---|---|---|---|
| Sem índices | 68.7 ms | 78.5 ms | 75.2 ms | **75.2 ms** |
| Com os 3 índices | 361.7 ms | 308.8 ms | 309.2 ms | **309.2 ms** |

Com índices, inserir as mesmas 100 000 linhas fica cerca de 4 vezes mais lento. Sem índices, cada linha é só acrescentada ao fim da tabela. Com índices, cada linha tem também de ser inserida, na posição certa, em cada B-tree: em `big_rental_rented_at` e em `big_rental_customer_rented_at`, e também no índice parcial `big_rental_open_customer`, porque estas linhas têm `returned_at IS NULL`. Isto obriga a descer cada árvore, por vezes a dividir páginas, e a escrever mais WAL.

É por isso que cada índice tem de se justificar com uma melhoria medida numa leitura: acelera as leituras que o usam, mas torna mais lentas todas as escritas na tabela e ocupa espaço (43 MB e 60 MB para os dois maiores, numa tabela de 99 MB).
