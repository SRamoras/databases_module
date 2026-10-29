# Exercício 05: Joins, agregação, subconsultas e CTEs

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `queries.sql` | As 10 consultas, cada uma com um comentário com o número e a pergunta. Sem funções de janela. |
| `README.md` | Este ficheiro: número de linhas e primeiras 5 linhas de cada resultado |

## Como correr

A partir da raiz do repositório:

```bash
./scripts/create-db.sh ex05 --pagila --reset
docker compose exec -T postgres psql -U postgres -d ex05 -v ON_ERROR_STOP=1 < exercises/05-queries/exercise/queries.sql
```

## Resumo

| # | Pergunta | Esperado | Obtido |
|---|----------|----------|--------|
| 1 | Filmes por categoria | 16 linhas, Drama e Music com 152 | 16 linhas, Drama 152, Music 152 |
| 2 | Receita por categoria por mês em 2025 | 192 linhas, Action jan/2025 = 314.94 | 192 linhas, 314.94 |
| 3 | Filmes nunca alugados | 42 | 42 |
| 4 | Clientes com as 5 classificações | 908 | 908 |
| 5 | Pares de atores com mais de 3 filmes | 143 | 143 |
| 6 | Países com mais de 20 clientes | 7 linhas, Mexico com 430 | 7 linhas, Mexico 430 |
| 7 | Clientes acima da média do país | 449 | 449 |
| 8 | Filmes mais longos por classificação | 14 | 14 |
| 9 | Clientes sem alugueres desde 2026-04-01 | 49 | 49 |
| 10 | Média de dias fora por categoria | 16 linhas, Sci-Fi 5.30 | 16 linhas, Sci-Fi 5.30 |

## Resultados

### 1. Filmes por categoria (16 linhas)

`LEFT JOIN` a partir de `category` para incluir categorias sem filmes, e `count(fc.film_id)` (não `count(*)`) para essas contarem 0.

```
  category   | films
-------------+-------
 Drama       |   152
 Music       |   152
 Travel      |   151
 Children    |   150
 Foreign     |   150
```

### 2. Receita por categoria por mês em 2025 (192 linhas)

Intervalo semiaberto `>= '2025-01-01' AND < '2026-01-01'` para apanhar o ano inteiro. 16 categorias × 12 meses = 192.

```
  category   |   month    | revenue
-------------+------------+---------
 Action      | 2025-01-01 |  314.94
 Action      | 2025-02-01 |  317.99
 Action      | 2025-03-01 |  370.90
 Action      | 2025-04-01 |  379.83
 Action      | 2025-05-01 |  384.76
```

### 3. Filmes nunca alugados (42 linhas)

`NOT EXISTS` sobre `inventory JOIN rental`: um filme sem cópias também não tem alugueres, por isso entra no resultado.

```
 film_id |         title
---------+------------------------
      14 | ALICE FANTASIA
      33 | APOLLO TEEN
      36 | ARGONAUTS TOWN
      38 | ARK RIDGEMONT
      41 | ARSENIC INDEPENDENCE
```

### 4. Clientes que alugaram filmes das 5 classificações (908 linhas)

`HAVING count(DISTINCT f.rating) = (SELECT count(DISTINCT rating) FROM film)`.

```
 customer_id | first_name  |  last_name
-------------+-------------+--------------
           1 | MARY        | SMITH
           2 | PATRICIA    | JOHNSON
           3 | LINDA       | WILLIAMS
           4 | BARBARA     | JONES
           5 | ELIZABETH   | BROWN
```

### 5. Pares de atores juntos em mais de 3 filmes (143 linhas)

Self join de `film_actor` com `fa2.actor_id > fa1.actor_id`: cada par aparece uma só vez e um ator nunca forma par consigo próprio.

```
 actor_id |        actor        | other_actor_id |    other_actor     | films
----------+---------------------+----------------+--------------------+-------
       27 | JULIA MCQUEEN       |             60 | HENRY BERRY        |     7
       15 | CUBA OLIVIER        |            198 | MARY KEITEL        |     6
       21 | KIRSTEN PALTROW     |            108 | WARREN NOLTE       |     6
       37 | VAL BOLGER          |            188 | ROCK DUKAKIS       |     6
       83 | BEN WILLIS          |            161 | HARVEY HOPE        |     6
```

### 6. Países com mais de 20 clientes (7 linhas)

O total por cliente é calculado numa CTE antes do join. Se se juntasse `payment` diretamente, cada cliente aparecia uma vez por pagamento e `count(*)` contava pagamentos em vez de clientes.

```
      country       | customers | total_paid
--------------------+-----------+------------
 Mexico             |       430 |   35650.03
 India              |        60 |   14182.51
 China              |        53 |   12389.30
 United States      |        36 |    8618.76
 Japan              |        31 |    7287.91
```

### 7. Clientes que pagaram mais do que o cliente médio do seu país (449 linhas)

Os clientes sem pagamentos ficam com `coalesce(..., 0)` antes de calcular a média, por isso também contam como 0 na média do país.

```
 customer_id | first_name  |  last_name   | country   |  paid  | country_avg
-------------+-------------+--------------+-----------+--------+-------------
         176 | JUNE        | CARROLL      | Algeria   | 280.26 |      253.64
         528 | CLAUDE      | HERZOG       | Angola    | 256.30 |      226.82
         359 | WILLIE      | MARKHAM      | Argentina | 293.17 |      241.67
          89 | JULIA       | FLORES       | Argentina | 284.22 |      241.67
         560 | JORDAN      | ARCHULETA    | Argentina | 273.27 |      241.67
```

### 8. Os filmes mais longos de cada classificação, com empates (14 linhas)

Subconsulta correlacionada: `f.length = (SELECT max(length) FROM film f2 WHERE f2.rating = f.rating)`. Os empates entram todos porque a comparação é por igualdade.

```
 rating |       title        | length
--------+--------------------+--------
 G      | CONTROL ANTHEM     |    185
 G      | DARN FORRESTER     |    185
 G      | MUSCLE BRIGHT      |    185
 PG     | WORST BANGER       |    185
 PG-13  | CHICAGO NORTH      |    185
```

### 9. Clientes sem nenhum aluguer a partir de 2026-04-01 (49 linhas)

```
 customer_id | first_name |  last_name
-------------+------------+-------------
           9 | MARGARET   | MOORE
          13 | KAREN      | JACKSON
          21 | MICHELLE   | CLARK
          46 | CATHERINE  | CAMPBELL
          52 | JULIE      | SANCHEZ
```

### 10. Média de dias fora por categoria (16 linhas)

`return_date - rental_date` dá um `interval`. `extract(epoch FROM ...) / 86400` converte-o em dias com parte decimal antes de calcular a média.

```
  category   | avg_days_out
-------------+--------------
 Sci-Fi      |         5.30
 Music       |         5.27
 Sports      |         5.26
 Drama       |         5.18
 Children    |         5.17
```
