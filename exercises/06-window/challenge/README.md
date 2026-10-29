# Desafio 06: Gaps and islands

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `islands.sql` | A consulta: ilha mais longa de cada cliente e os 10 clientes com as ilhas mais longas |
| `README.md` | Este ficheiro |

## Como correr

A partir da raiz do repositório:

```bash
./scripts/create-db.sh ch06 --pagila --reset
docker compose exec -T postgres psql -U postgres -d ch06 -v ON_ERROR_STOP=1 < exercises/06-window/challenge/islands.sql
```

## Resultado

```
 customer_id | first_month | last_month | months
-------------+-------------+------------+--------
          70 | 2023-06     | 2024-12    |     19
         547 | 2022-05     | 2023-10    |     18
         567 | 2022-06     | 2023-11    |     18
          33 | 2023-07     | 2024-11    |     17
         158 | 2022-11     | 2024-03    |     17
         299 | 2022-05     | 2023-09    |     17
         443 | 2023-07     | 2024-11    |     17
         533 | 2023-04     | 2024-08    |     17
         740 | 2024-07     | 2025-11    |     17
         556 | 2023-09     | 2024-12    |     16
(10 rows)
```

A primeira linha é o cliente 70 com 19 meses (de 2023-06 a 2024-12) e a décima é o cliente 556 com 16 meses, como pedido. Os empates em `months` estão ordenados por `customer_id`.

## A técnica: diferença entre o mês e o `row_number`

**1. Um mês por cliente.** `SELECT DISTINCT customer_id, mês` dá os meses em que cada cliente alugou pelo menos um filme. Cada mês é convertido num número sequencial, `ano * 12 + mês - 1`. Assim, dois meses consecutivos diferem sempre exatamente 1, mesmo na passagem de dezembro para janeiro (2023-12 → 2024-01 dá 24287 → 24288).

**2. A diferença identifica a ilha.** Para cada cliente, numeram-se os meses por ordem com `row_number()` e calcula-se `month_no - row_number`:

| mês | month_no | row_number | diferença | ilha |
|-----|----------|------------|-----------|------|
| 2022-05 | 24268 | 1 | 24267 | A |
| 2022-06 | 24269 | 2 | 24267 | A |
| 2022-07 | 24270 | 3 | 24267 | A |
| 2022-10 | 24273 | 4 | 24269 | B |
| 2022-11 | 24274 | 5 | 24269 | B |

Dentro de uma ilha, o mês e o `row_number` sobem os dois de 1 em 1, por isso a diferença fica constante. Quando há um buraco (aqui faltam agosto e setembro), o mês salta mais do que o `row_number` e a diferença muda. Cada valor da diferença é uma ilha.

Os meses em que ninguém alugou, como março e abril de 2022, não precisam de tratamento especial: não aparecem em `active_month`, por isso são um buraco como outro qualquer e partem a ilha.

**3. Agrupar e escolher.** `GROUP BY customer_id, diferença` dá cada ilha, com `min` (primeiro mês), `max` (último mês) e `count` (número de meses). `row_number() OVER (PARTITION BY customer_id ORDER BY months DESC, first_no)` escolhe a ilha mais longa de cada cliente, e em caso de empate a mais antiga. No fim ordena-se por `months DESC, customer_id` e fica-se com as 10 primeiras.

Só se usam funções de janela (`row_number`), `DISTINCT` e `GROUP BY`. Não há código procedimental nem CTE recursiva.

Nota: o mês é calculado com `extract` sobre `rental_date` (`timestamptz`) no fuso horário da sessão, que no contentor é UTC. Num fuso diferente, um aluguer feito perto da meia-noite do último dia do mês podia mudar de mês.
