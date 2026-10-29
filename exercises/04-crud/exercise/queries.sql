-- Exercício 04: CRUD, upsert e paginação sobre uma cópia nova de Pagila (ex04).
-- Correr de cima para baixo:
--   docker compose exec -T postgres psql -U postgres -d ex04 -v ON_ERROR_STOP=1 < exercises/04-crud/exercise/queries.sql

-- 1. Filmes PG-13 com mais de 120 minutos, ordenados por título.
SELECT title, length, rating
FROM film
WHERE rating = 'PG-13' AND length > 120
ORDER BY title;

-- 2. Atores cujo apelido contém "son", sem distinguir maiúsculas.
SELECT actor_id, first_name, last_name
FROM actor
WHERE last_name ILIKE '%son%'
ORDER BY last_name, first_name;

-- 3. Alugueres ainda não devolvidos (= NULL nunca é verdadeiro: tem de ser IS NULL).
SELECT rental_id, rental_date, inventory_id, customer_id
FROM rental
WHERE return_date IS NULL
ORDER BY rental_id;

-- 4. Valores distintos de rental_duration, por ordem crescente.
SELECT DISTINCT rental_duration
FROM film
ORDER BY rental_duration;

-- 5. Terceira página de filmes por título, 10 por página (salta as páginas 1 e 2).
SELECT film_id, title
FROM film
ORDER BY title
LIMIT 10 OFFSET 20;

-- 6. Alugueres em janeiro de 2026, escrito de duas formas.
SELECT count(*) AS with_between
FROM rental
WHERE rental_date BETWEEN '2026-01-01' AND '2026-01-31';

SELECT count(*) AS with_half_open_range
FROM rental
WHERE rental_date >= '2026-01-01' AND rental_date < '2026-02-01';
-- rental_date é um timestamp. '2026-01-31' é convertido para '2026-01-31 00:00:00',
-- por isso o BETWEEN (que inclui os dois extremos) só apanha a meia-noite exata do dia 31
-- e deixa de fora todos os alugueres feitos durante o dia 31 (746 em vez de 781).
-- A forma correta é o intervalo semiaberto >= início do mês e < início do mês seguinte:
-- apanha o mês inteiro, seja qual for a precisão do timestamp.

-- 7. Inserir a atriz ADA LOVELACE e obter o actor_id gerado.
INSERT INTO actor (first_name, last_name)
VALUES ('ADA', 'LOVELACE')
RETURNING actor_id, first_name, last_name;

-- 8. Subir 0.50 ao rental_rate dos filmes NC-17 com menos de 60 minutos, com contagem prévia.
BEGIN;
SELECT count(*)
FROM film
WHERE rating = 'NC-17' AND length < 60;

UPDATE film
SET rental_rate = rental_rate + 0.50
WHERE rating = 'NC-17' AND length < 60
RETURNING film_id, title, rental_rate;
COMMIT;

-- 9. Upsert: dar um prémio ao ator 1 (insere com 1 ou soma 1 se já existir). Corre duas vezes.
CREATE TABLE actor_award (
    actor_id integer PRIMARY KEY REFERENCES actor,
    awards   integer NOT NULL DEFAULT 0
);

INSERT INTO actor_award (actor_id, awards) VALUES (1, 1)
ON CONFLICT (actor_id) DO UPDATE SET awards = actor_award.awards + 1
RETURNING actor_id, awards;

INSERT INTO actor_award (actor_id, awards) VALUES (1, 1)
ON CONFLICT (actor_id) DO UPDATE SET awards = actor_award.awards + 1
RETURNING actor_id, awards;

-- 10. Inserir o ator 2 com 5 prémios, sem tocar na linha se já existir. Corre duas vezes.
INSERT INTO actor_award (actor_id, awards) VALUES (2, 5)
ON CONFLICT (actor_id) DO NOTHING
RETURNING actor_id, awards;

INSERT INTO actor_award (actor_id, awards) VALUES (2, 5)
ON CONFLICT (actor_id) DO NOTHING
RETURNING actor_id, awards;

-- 11. Três pagamentos de teste numa só instrução.
INSERT INTO payment (customer_id, staff_id, rental_id, amount, payment_date)
VALUES (1, 2, 76, 0.01, '2026-07-30 12:00+00'),
       (1, 2, 76, 0.01, '2026-07-30 12:00+00'),
       (1, 2, 76, 0.01, '2026-07-30 12:00+00')
RETURNING payment_id;

-- 12. Apagar os 3 pagamentos de teste, com contagem prévia, numa transação.
BEGIN;
SELECT count(*)
FROM payment
WHERE customer_id = 1 AND staff_id = 2 AND rental_id = 76
  AND amount = 0.01 AND payment_date = '2026-07-30 12:00+00';

DELETE FROM payment
WHERE customer_id = 1 AND staff_id = 2 AND rental_id = 76
  AND amount = 0.01 AND payment_date = '2026-07-30 12:00+00'
RETURNING payment_id, customer_id, amount, payment_date;
COMMIT;
