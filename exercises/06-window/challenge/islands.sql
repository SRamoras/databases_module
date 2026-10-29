-- Desafio 06: a ilha mais longa de meses consecutivos com alugueres, por cliente (cópia nova de Pagila, ch06).
-- Só funções de janela e operações de conjuntos: sem código procedimental nem CTE recursiva.
-- Correr:
--   docker compose exec -T postgres psql -U postgres -d ch06 -v ON_ERROR_STOP=1 < exercises/06-window/challenge/islands.sql

WITH active_month AS (
    -- Um mês por cliente em que alugou pelo menos um filme, como número sequencial
    -- (ano * 12 + mês), para que meses consecutivos difiram exatamente 1, mesmo na mudança de ano.
    SELECT DISTINCT customer_id,
           (extract(year FROM rental_date) * 12 + extract(month FROM rental_date) - 1)::integer AS month_no
    FROM rental
),
grouped AS (
    -- Numa ilha, month_no e row_number sobem os dois de 1 em 1, por isso a diferença é constante.
    -- Depois de um buraco, month_no salta mais do que row_number e a diferença muda: nova ilha.
    SELECT customer_id, month_no,
           month_no - row_number() OVER (PARTITION BY customer_id ORDER BY month_no) AS island
    FROM active_month
),
island AS (
    SELECT customer_id, min(month_no) AS first_no, max(month_no) AS last_no, count(*) AS months
    FROM grouped
    GROUP BY customer_id, island
),
longest AS (
    -- A ilha mais longa de cada cliente; em empate, a mais antiga.
    SELECT *, row_number() OVER (PARTITION BY customer_id ORDER BY months DESC, first_no) AS pick
    FROM island
)
SELECT customer_id,
       to_char(make_date(first_no / 12, first_no % 12 + 1, 1), 'YYYY-MM') AS first_month,
       to_char(make_date(last_no / 12, last_no % 12 + 1, 1), 'YYYY-MM') AS last_month,
       months
FROM longest
WHERE pick = 1
ORDER BY months DESC, customer_id
LIMIT 10;
