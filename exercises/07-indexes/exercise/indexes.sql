-- Índices mantidos depois de medir (ver README.md).

-- Q1: índice parcial só com as linhas por devolver (~3% da tabela), por cliente.
-- A contagem faz-se só com o índice (Index Only Scan).
CREATE INDEX big_rental_open_customer ON big_rental (customer_id) WHERE returned_at IS NULL;

-- Q2 (e Q3 reescrita): intervalo em rented_at, já pela ordem do ORDER BY.
CREATE INDEX big_rental_rented_at ON big_rental (rented_at);

-- Q5: igualdade em customer_id primeiro, intervalo em rented_at depois.
CREATE INDEX big_rental_customer_rented_at ON big_rental (customer_id, rented_at);

ANALYZE big_rental;
