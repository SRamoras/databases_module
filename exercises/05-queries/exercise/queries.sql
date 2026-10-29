-- Exercício 05: joins, agregação, subconsultas e CTEs sobre uma cópia nova de Pagila (ex05).
-- Sem funções de janela. Correr:
--   docker compose exec -T postgres psql -U postgres -d ex05 -v ON_ERROR_STOP=1 < exercises/05-queries/exercise/queries.sql

-- 1. Número de filmes por categoria, incluindo categorias sem filmes,
--    mais filmes primeiro e depois por nome da categoria.
SELECT c.name AS category, count(fc.film_id) AS films
FROM category c
LEFT JOIN film_category fc ON fc.category_id = c.category_id
GROUP BY c.category_id, c.name
ORDER BY films DESC, category;

-- 2. Receita por categoria por mês em 2025 (pela payment_date).
--    Um filme em várias categorias conta em cada uma delas.
SELECT c.name AS category,
       date_trunc('month', p.payment_date)::date AS month,
       sum(p.amount) AS revenue
FROM payment p
JOIN rental r         ON r.rental_id = p.rental_id
JOIN inventory i      ON i.inventory_id = r.inventory_id
JOIN film_category fc ON fc.film_id = i.film_id
JOIN category c       ON c.category_id = fc.category_id
WHERE p.payment_date >= '2025-01-01' AND p.payment_date < '2026-01-01'
GROUP BY c.name, month
ORDER BY category, month;

-- 3. Filmes que nunca foram alugados, incluindo filmes sem nenhuma cópia em nenhuma loja.
SELECT f.film_id, f.title
FROM film f
WHERE NOT EXISTS (
    SELECT 1
    FROM inventory i
    JOIN rental r ON r.inventory_id = i.inventory_id
    WHERE i.film_id = f.film_id
)
ORDER BY f.title;

-- 4. Clientes que alugaram filmes das 5 classificações.
SELECT cu.customer_id, cu.first_name, cu.last_name
FROM customer cu
JOIN rental r    ON r.customer_id = cu.customer_id
JOIN inventory i ON i.inventory_id = r.inventory_id
JOIN film f      ON f.film_id = i.film_id
GROUP BY cu.customer_id, cu.first_name, cu.last_name
HAVING count(DISTINCT f.rating) = (SELECT count(DISTINCT rating) FROM film)
ORDER BY cu.customer_id;

-- 5. Pares de atores que entraram juntos em mais de 3 filmes, cada par uma só vez (self join).
SELECT a1.actor_id AS actor_id, a1.first_name || ' ' || a1.last_name AS actor,
       a2.actor_id AS other_actor_id, a2.first_name || ' ' || a2.last_name AS other_actor,
       count(*) AS films
FROM film_actor fa1
JOIN film_actor fa2 ON fa2.film_id = fa1.film_id
                   AND fa2.actor_id > fa1.actor_id  -- cada par uma vez, sem o ator consigo próprio
JOIN actor a1 ON a1.actor_id = fa1.actor_id
JOIN actor a2 ON a2.actor_id = fa2.actor_id
GROUP BY a1.actor_id, a2.actor_id
HAVING count(*) > 3
ORDER BY films DESC, a1.actor_id, a2.actor_id;

-- 6. Países com mais de 20 clientes, com o número de clientes e o total que pagaram,
--    mais clientes primeiro. O total por cliente é calculado antes do join com o país,
--    para que os pagamentos não multipliquem a contagem de clientes.
WITH customer_total AS (
    SELECT customer_id, sum(amount) AS paid
    FROM payment
    GROUP BY customer_id
)
SELECT co.country, count(*) AS customers, coalesce(sum(ct.paid), 0) AS total_paid
FROM customer cu
JOIN address a  ON a.address_id = cu.address_id
JOIN city ci    ON ci.city_id = a.city_id
JOIN country co ON co.country_id = ci.country_id
LEFT JOIN customer_total ct ON ct.customer_id = cu.customer_id
GROUP BY co.country_id, co.country
HAVING count(*) > 20
ORDER BY customers DESC, co.country;

-- 7. Clientes que pagaram mais no total do que o cliente médio do seu país.
--    Um cliente sem pagamentos conta como 0 (também na média do país).
WITH customer_total AS (
    SELECT cu.customer_id, cu.first_name, cu.last_name, ci.country_id,
           coalesce((SELECT sum(p.amount) FROM payment p WHERE p.customer_id = cu.customer_id), 0) AS paid
    FROM customer cu
    JOIN address a ON a.address_id = cu.address_id
    JOIN city ci   ON ci.city_id = a.city_id
),
country_avg AS (
    SELECT country_id, avg(paid) AS avg_paid
    FROM customer_total
    GROUP BY country_id
)
SELECT ct.customer_id, ct.first_name, ct.last_name, co.country,
       ct.paid, round(ca.avg_paid, 2) AS country_avg
FROM customer_total ct
JOIN country_avg ca ON ca.country_id = ct.country_id
JOIN country co     ON co.country_id = ct.country_id
WHERE ct.paid > ca.avg_paid
ORDER BY co.country, ct.paid DESC, ct.customer_id;

-- 8. Os filmes mais longos de cada classificação, incluindo empates (subconsulta correlacionada).
SELECT f.rating, f.title, f.length
FROM film f
WHERE f.length = (SELECT max(f2.length) FROM film f2 WHERE f2.rating = f.rating)
ORDER BY f.rating, f.title;

-- 9. Clientes sem nenhum aluguer a partir de 2026-04-01.
SELECT cu.customer_id, cu.first_name, cu.last_name
FROM customer cu
WHERE NOT EXISTS (
    SELECT 1 FROM rental r
    WHERE r.customer_id = cu.customer_id AND r.rental_date >= '2026-04-01'
)
ORDER BY cu.customer_id;

-- 10. Para cada categoria, o número médio de dias que um filme fica fora
--     (return_date - rental_date, só alugueres devolvidos), com 2 casas decimais, maior primeiro.
--     A diferença de dois timestamptz é um interval; extract(epoch) dá os segundos, / 86400 dá os dias.
SELECT c.name AS category,
       round(avg(extract(epoch FROM r.return_date - r.rental_date) / 86400), 2) AS avg_days_out
FROM rental r
JOIN inventory i      ON i.inventory_id = r.inventory_id
JOIN film_category fc ON fc.film_id = i.film_id
JOIN category c       ON c.category_id = fc.category_id
WHERE r.return_date IS NOT NULL
GROUP BY c.category_id, c.name
ORDER BY avg_days_out DESC, category;
