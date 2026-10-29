# Exercício 04: CRUD, upsert e paginação

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `queries.sql` | As 12 operações, numeradas com `-- 1.` a `-- 12.` |
| `README.md` | Este ficheiro: o output de cada operação |

## Como correr

A partir da raiz do repositório, numa cópia nova de Pagila:

```bash
./scripts/create-db.sh ex04 --pagila --reset
docker compose exec -T postgres psql -U postgres -d ex04 -v ON_ERROR_STOP=1 < exercises/04-crud/exercise/queries.sql
```

O script corre do início ao fim sem erros. As operações 7 a 12 alteram dados, por isso para repetir é preciso recriar a cópia com `--reset`.

## Resultados

### 1. Filmes PG-13 com mais de 120 minutos, por título

118 linhas, de `APOLLO TEEN` a `WRONG BEHAVIOR`.

```
            title            | length | rating
-----------------------------+--------+--------
 APOLLO TEEN                 |    153 | PG-13
 ARACHNOPHOBIA ROLLERCOASTER |    147 | PG-13
 ...
 VOICE PEACH                 |    139 | PG-13
 WORLD LEATHERNECKS          |    171 | PG-13
 WRONG BEHAVIOR              |    178 | PG-13
(118 rows)
```

### 2. Atores com `son` no apelido (sem distinguir maiúsculas)

9 linhas.

```
 actor_id | first_name | last_name
----------+------------+-----------
      154 | MERYL      | GIBSON
       65 | ANGELA     | HUDSON
      146 | ALBERT     | JOHANSSON
        8 | MATTHEW    | JOHANSSON
       64 | RAY        | JOHANSSON
       61 | CHRISTIAN  | NEESON
       62 | JAYNE      | NEESON
        6 | BETTE      | NICHOLSON
      168 | WILL       | WILSON
(9 rows)
```

### 3. Alugueres ainda não devolvidos

241 linhas.

```
 rental_id |          rental_date          | inventory_id | customer_id
-----------+-------------------------------+--------------+-------------
     11496 | 2022-02-14 15:16:03+00        |         2047 |         155
 ...
     87534 | 2026-07-27 04:40:26.294744+00 |          324 |         235
(241 rows)
```

### 4. Valores distintos de `rental_duration`

5 linhas, de 3 a 7.

```
 rental_duration
-----------------
               3
               4
               5
               6
               7
(5 rows)
```

### 5. Terceira página de filmes por título (10 por página)

10 linhas, de `AMERICAN CIRCUS` a `ANYTHING SAVANNAH`.

```
 film_id |        title
---------+----------------------
      21 | AMERICAN CIRCUS
      22 | AMISTAD MIDSUMMER
      23 | ANACONDA CONFESSIONS
      24 | ANALYZE HOOSIERS
      25 | ANGELS LIFE
      26 | ANNIE IDENTITY
      27 | ANONYMOUS HUMAN
      28 | ANTHEM LUKE
      29 | ANTITRUST TOMATOES
      30 | ANYTHING SAVANNAH
(10 rows)
```

### 6. Alugueres em janeiro de 2026

```
 with_between
--------------
          746
(1 row)

 with_half_open_range
----------------------
                  781
(1 row)
```

`rental_date` é um timestamp, por isso `'2026-01-31'` é lido como `2026-01-31 00:00:00`. O `BETWEEN` inclui os dois extremos, mas só apanha a meia-noite exata do dia 31: os alugueres feitos durante o dia 31 ficam de fora (746 em vez de 781). O correto é o intervalo semiaberto `>= '2026-01-01' AND < '2026-02-01'`, que apanha o mês inteiro seja qual for a precisão do timestamp.

### 7. Inserir `ADA LOVELACE`

```
 actor_id | first_name | last_name
----------+------------+-----------
      201 | ADA        | LOVELACE
(1 row)

INSERT 0 1
```

### 8. Subir o `rental_rate` dos filmes NC-17 com menos de 60 minutos

A contagem e o `UPDATE` afetam as mesmas 21 linhas, por isso fez-se `COMMIT`.

```
BEGIN
 count
-------
    21
(1 row)

 film_id |        title        | rental_rate
---------+---------------------+-------------
       3 | ADAPTATION HOLES    |        3.49
      15 | ALIEN CENTER        |        3.49
 ...
     981 | WOLVES DESIRE       |        1.49
    1000 | ZORRO ARK           |        5.49
(21 rows)

UPDATE 21
COMMIT
```

### 9. Upsert de um prémio para o ator 1 (duas vezes)

A primeira execução insere com 1 e a segunda soma 1: `awards` fica 2.

```
CREATE TABLE
 actor_id | awards
----------+--------
        1 |      1
(1 row)

INSERT 0 1
 actor_id | awards
----------+--------
        1 |      2
(1 row)

INSERT 0 1
```

### 10. Ator 2 com 5 prémios, `ON CONFLICT DO NOTHING` (duas vezes)

A primeira execução insere 1 linha e a segunda 0.

```
 actor_id | awards
----------+--------
        2 |      5
(1 row)

INSERT 0 1
 actor_id | awards
----------+--------
(0 rows)

INSERT 0 0
```

### 11. Três pagamentos de teste numa instrução

```
 payment_id
------------
     102095
     102096
     102097
(3 rows)

INSERT 0 3
```

### 12. Apagar os pagamentos de teste

A contagem e o `DELETE` afetam as mesmas 3 linhas, por isso fez-se `COMMIT`.

```
BEGIN
 count
-------
     3
(1 row)

 payment_id | customer_id | amount |      payment_date
------------+-------------+--------+------------------------
     102095 |           1 |   0.01 | 2026-07-30 12:00:00+00
     102096 |           1 |   0.01 | 2026-07-30 12:00:00+00
     102097 |           1 |   0.01 | 2026-07-30 12:00:00+00
(3 rows)

DELETE 3
COMMIT
```
