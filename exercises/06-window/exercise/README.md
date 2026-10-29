# Exercício 06: Funções de janela e vista materializada

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `queries.sql` | As 6 tarefas, cada uma com um comentário com o número |
| `README.md` | Este ficheiro: número de linhas e primeiras 5 linhas de cada resultado, e os passos da tarefa 6 |

## Como correr

A partir da raiz do repositório:

```bash
./scripts/create-db.sh ex06 --pagila --reset
docker compose exec -T postgres psql -U postgres -d ex06 -v ON_ERROR_STOP=1 < exercises/06-window/exercise/queries.sql
```

A tarefa 6 cria a vista e insere um pagamento. Para repetir, é preciso recriar a cópia com `--reset`.

## Resumo

| # | Tarefa | Esperado | Obtido |
|---|--------|----------|--------|
| 1 | Top 3 filmes por categoria | 56 linhas | 56 |
| 2 | Receita diária de julho de 2026 com acumulado | 28 linhas, último acumulado 2409.88 | 28, 2409.88 |
| 3 | Receita mensal com variação | 55 linhas; jul/2026 2409.88, anterior 2105.73, +304.15, 14.4% | igual |
| 4 | Ranking de clientes por loja | 999 linhas; 468 primeiro na loja 1 (344.06), 526 na loja 2 (358.12) | igual |
| 5 | Top 5 clientes por loja | 10 linhas | 10 |
| 6 | Vista materializada | só muda depois do refresh | 2409.88 → (pagamento de 100) → 2409.88 → refresh → 2509.88 |

## Resultados

### 1. Os 3 filmes mais alugados de cada categoria (56 linhas)

`dense_rank()` por categoria: os empates partilham a posição e as posições não saltam (1, 1, 2, 3), por isso aparecem todos os filmes das posições 1 a 3. Por isso há mais de 16 × 3 = 48 linhas. Com `rank()` um empate no 1.º lugar fazia saltar para o 3.º, e com `row_number()` os empates eram cortados arbitrariamente.

```
  category   | position |        title         | rentals
-------------+----------+----------------------+---------
 Action      |        1 | CAT CONEHEADS        |     123
 Action      |        2 | SEABISCUIT PUNK      |      96
 Action      |        3 | IDOLS SNATCHERS      |      92
 Animation   |        1 | GILMORE BOILED       |     102
 Animation   |        1 | GRIT CLOCKWORK       |     102
```

### 2. Receita por dia em julho de 2026 com total acumulado (28 linhas)

`sum(revenue) OVER (ORDER BY day)` soma desde o primeiro dia até ao dia da linha.

```
    day     | revenue | running_total
------------+---------+---------------
 2026-07-01 |   67.78 |         67.78
 2026-07-02 |   89.62 |        157.40
 2026-07-03 |   61.78 |        219.18
 2026-07-04 |   97.66 |        316.84
 2026-07-05 |   46.81 |        363.65
 ...
 2026-07-28 |  426.58 |       2409.88
```

### 3. Receita por mês com variação face ao mês anterior (55 linhas)

`lag(revenue) OVER (ORDER BY month)` dá a receita do mês anterior. O primeiro mês não tem anterior, por isso a variação fica vazia.

```
   month    | revenue  | previous_revenue |  change  | change_pct
------------+----------+------------------+----------+------------
 2022-01-01 |  3094.78 |                  |          |
 2022-02-01 | 10164.97 |          3094.78 |  7070.19 |      228.5
 2022-03-01 | 11413.86 |         10164.97 |  1248.89 |       12.3
 2022-04-01 | 10759.52 |         11413.86 |  -654.34 |       -5.7
 2022-05-01 | 11347.28 |         10759.52 |   587.76 |        5.5
 ...
 2026-06-01 |  2105.73 |          2380.18 |  -274.45 |      -11.5
 2026-07-01 |  2409.88 |          2105.73 |   304.15 |       14.4
```

### 4. Posição de cada cliente no ranking da sua loja (999 linhas)

`LEFT JOIN payment` e `coalesce(sum(amount), 0)` para os clientes sem pagamentos contarem como 0. `rank() OVER (PARTITION BY store_id ORDER BY total_paid DESC)` faz os empatados partilharem a posição.

```
 store_id | customer_id | first_name  |  last_name   | total_paid | position
----------+-------------+-------------+--------------+------------+----------
        1 |         468 | TIM         | CARY         |     344.06 |        1
        1 |         380 | RUSSELL     | BRINSON      |     324.04 |        2
        1 |         368 | HARRY       | ARCE         |     323.17 |        3
        1 |         295 | DAISY       | BATES        |     322.12 |        4
        1 |          22 | LAURA       | RODRIGUEZ    |     320.17 |        5
 ...
        2 |         526 | KARL        | SEAL         |     358.12 |        1
```

### 5. Os 5 melhores clientes de cada loja (10 linhas)

```
 store_id | position | customer_id | first_name | last_name | total_paid
----------+----------+-------------+------------+-----------+------------
        1 |        1 |         468 | TIM        | CARY      |     344.06
        1 |        2 |         380 | RUSSELL    | BRINSON   |     324.04
        1 |        3 |         368 | HARRY      | ARCE      |     323.17
        1 |        4 |         295 | DAISY      | BATES     |     322.12
        1 |        5 |          22 | LAURA      | RODRIGUEZ |     320.17
```

### 6. Receita mensal numa vista materializada

O enunciado não descreve a tarefa 6. Segui o objetivo ("manter um relatório numa vista materializada"), o critério "a vista materializada só muda depois do refresh" e a sessão 15, que usa a vista `monthly_revenue` e diz que é a do exercício 06.

Passos e output:

```
-- criar a vista e o índice único (obrigatório para REFRESH ... CONCURRENTLY)
SELECT 55
CREATE INDEX

-- 6a. antes: julho de 2026 na vista
   month    | revenue
------------+---------
 2026-07-01 | 2409.88
(1 row)

-- 6b. novo pagamento de 100.00 em julho de 2026
 payment_id | amount |      payment_date
------------+--------+------------------------
     102095 | 100.00 | 2026-07-30 12:00:00+00
(1 row)

INSERT 0 1

-- 6c. a vista ainda não mudou; a consulta direta já vê o pagamento
   source   | revenue
------------+---------
 view       | 2409.88
 live query | 2509.88
(2 rows)

-- 6d.
REFRESH MATERIALIZED VIEW

-- 6e. depois do refresh, a vista inclui o pagamento
   month    | revenue
------------+---------
 2026-07-01 | 2509.88
(1 row)
```

A vista materializada guarda o resultado da consulta como uma tabela. Por isso é rápida de ler, mas fica desatualizada até ao `REFRESH`: depois do `INSERT` continuava com 2409.88, e só passou a 2509.88 depois do refresh. O `CONCURRENTLY` deixa os leitores continuar a ler a versão antiga durante o refresh, e por isso exige um índice único na vista.
