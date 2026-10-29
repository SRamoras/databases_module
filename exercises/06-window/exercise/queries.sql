-- Exercício 06: funções de janela e vista materializada sobre uma cópia nova de Pagila (ex06).
-- Correr:
--   docker compose exec -T postgres psql -U postgres -d ex06 -v ON_ERROR_STOP=1 < exercises/06-window/exercise/queries.sql

-- 1. Os 3 filmes mais alugados de cada categoria. Empates partilham a posição
--    e todos os filmes nas posições 1 a 3 aparecem (dense_rank não salta posições).
WITH film_rentals AS (
    SELECT c.name AS category, f.title, count(*) AS rentals
    FROM rental r
    JOIN inventory i      ON i.inventory_id = r.inventory_id
    JOIN film f           ON f.film_id = i.film_id
    JOIN film_category fc ON fc.film_id = f.film_id
    JOIN category c       ON c.category_id = fc.category_id
    GROUP BY c.category_id, c.name, f.film_id, f.title
),
ranked AS (
    SELECT category, title, rentals,
           dense_rank() OVER (PARTITION BY category ORDER BY rentals DESC) AS position
    FROM film_rentals
)
SELECT category, position, title, rentals
FROM ranked
WHERE position <= 3
ORDER BY category, position, title;

-- 2. Receita por dia em julho de 2026, com o total acumulado do mês.
SELECT day, revenue,
       sum(revenue) OVER (ORDER BY day) AS running_total
FROM (
    SELECT payment_date::date AS day, sum(amount) AS revenue
    FROM payment
    WHERE payment_date >= '2026-07-01' AND payment_date < '2026-08-01'
    GROUP BY payment_date::date
) daily
ORDER BY day;

-- 3. Receita por mês em todo o conjunto de dados, com a variação face ao mês anterior
--    em valor e em percentagem (1 casa decimal).
SELECT month, revenue,
       lag(revenue) OVER w AS previous_revenue,
       revenue - lag(revenue) OVER w AS change,
       round(100 * (revenue - lag(revenue) OVER w) / lag(revenue) OVER w, 1) AS change_pct
FROM (
    SELECT date_trunc('month', payment_date)::date AS month, sum(amount) AS revenue
    FROM payment
    GROUP BY 1
) monthly
WINDOW w AS (ORDER BY month)
ORDER BY month;

-- 4. Posição de cada cliente no ranking da sua loja pelo total pago.
--    Clientes sem pagamentos contam como 0; empates partilham a posição (rank).
WITH customer_total AS (
    SELECT cu.customer_id, cu.store_id, cu.first_name, cu.last_name,
           coalesce(sum(p.amount), 0) AS total_paid
    FROM customer cu
    LEFT JOIN payment p ON p.customer_id = cu.customer_id
    GROUP BY cu.customer_id
)
SELECT store_id, customer_id, first_name, last_name, total_paid,
       rank() OVER (PARTITION BY store_id ORDER BY total_paid DESC) AS position
FROM customer_total
ORDER BY store_id, position, customer_id;

-- 5. Os 5 melhores clientes de cada loja pelo total pago.
WITH customer_total AS (
    SELECT cu.customer_id, cu.store_id, cu.first_name, cu.last_name,
           coalesce(sum(p.amount), 0) AS total_paid
    FROM customer cu
    LEFT JOIN payment p ON p.customer_id = cu.customer_id
    GROUP BY cu.customer_id
),
ranked AS (
    SELECT *, rank() OVER (PARTITION BY store_id ORDER BY total_paid DESC) AS position
    FROM customer_total
)
SELECT store_id, position, customer_id, first_name, last_name, total_paid
FROM ranked
WHERE position <= 5
ORDER BY store_id, position, customer_id;

-- 6. Relatório de receita mensal numa vista materializada (a mesma que a sessão 15 usa).
--    Mostra que a vista guarda o resultado e só muda depois do REFRESH.
CREATE MATERIALIZED VIEW monthly_revenue AS
SELECT date_trunc('month', payment_date)::date AS month, sum(amount) AS revenue
FROM payment
GROUP BY 1;

-- O índice único é obrigatório para REFRESH ... CONCURRENTLY.
CREATE UNIQUE INDEX monthly_revenue_month ON monthly_revenue (month);

-- 6a. Antes: julho de 2026 na vista.
SELECT month, revenue FROM monthly_revenue WHERE month = '2026-07-01';

-- 6b. Um pagamento novo em julho de 2026.
INSERT INTO payment (customer_id, staff_id, rental_id, amount, payment_date)
VALUES (1, 2, 76, 100.00, '2026-07-30 12:00+00')
RETURNING payment_id, amount, payment_date;

-- 6c. A vista continua igual (está desatualizada), mas a consulta direta já vê o pagamento.
SELECT 'view' AS source, revenue FROM monthly_revenue WHERE month = '2026-07-01'
UNION ALL
SELECT 'live query', sum(amount) FROM payment
WHERE payment_date >= '2026-07-01' AND payment_date < '2026-08-01';

-- 6d. Refresh sem bloquear leitores.
REFRESH MATERIALIZED VIEW CONCURRENTLY monthly_revenue;

-- 6e. Depois: a vista já inclui o pagamento novo.
SELECT month, revenue FROM monthly_revenue WHERE month = '2026-07-01';
