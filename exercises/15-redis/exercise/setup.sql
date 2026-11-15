-- The materialised view of exercise 06, refreshed by refresh.py.
-- Run once on ex15 (see the README).
CREATE MATERIALIZED VIEW monthly_revenue AS
SELECT date_trunc('month', payment_date)::date AS month, sum(amount) AS revenue
FROM payment
GROUP BY 1;

-- REFRESH ... CONCURRENTLY needs a unique index
CREATE UNIQUE INDEX ON monthly_revenue (month);
