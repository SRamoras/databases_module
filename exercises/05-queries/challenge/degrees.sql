-- Desafio 05: graus de separação entre atores com WITH RECURSIVE (cópia nova de Pagila, ch05).
-- Dois atores estão ligados quando entraram juntos em pelo menos 3 filmes.
-- Correr:
--   docker compose exec -T postgres psql -U postgres -d ch05 -v ON_ERROR_STOP=1 < exercises/05-queries/challenge/degrees.sql

-- Tarefa 2: atores a 3 graus ou menos do ator 1, com a distância mais curta.
WITH RECURSIVE
edge (actor_id, other_actor_id) AS (
    -- Tarefa 1: cada par ligado, nos dois sentidos (fa2.actor_id <> fa1.actor_id dá (a, b) e (b, a)).
    SELECT fa1.actor_id, fa2.actor_id
    FROM film_actor fa1
    JOIN film_actor fa2 ON fa2.film_id = fa1.film_id AND fa2.actor_id <> fa1.actor_id
    GROUP BY fa1.actor_id, fa2.actor_id
    HAVING count(*) >= 3
),
search (actor_id, distance, path) AS (
    SELECT 1, 0, ARRAY[1]
    UNION ALL
    SELECT e.other_actor_id, s.distance + 1, s.path || e.other_actor_id
    FROM search s
    JOIN edge e ON e.actor_id = s.actor_id
    WHERE s.distance < 3                          -- para ao fim de 3 graus
      AND e.other_actor_id <> ALL (s.path)        -- nunca volta a um ator do mesmo caminho
)
SELECT a.actor_id, a.first_name, a.last_name, min(s.distance) AS distance
FROM search s
JOIN actor a ON a.actor_id = s.actor_id
WHERE s.actor_id <> 1
GROUP BY a.actor_id, a.first_name, a.last_name
ORDER BY distance, a.actor_id;

-- Número de atores a cada distância (o resumo do README): a mesma pesquisa, agrupada.
WITH RECURSIVE
edge (actor_id, other_actor_id) AS (
    SELECT fa1.actor_id, fa2.actor_id
    FROM film_actor fa1
    JOIN film_actor fa2 ON fa2.film_id = fa1.film_id AND fa2.actor_id <> fa1.actor_id
    GROUP BY fa1.actor_id, fa2.actor_id
    HAVING count(*) >= 3
),
search (actor_id, distance, path) AS (
    SELECT 1, 0, ARRAY[1]
    UNION ALL
    SELECT e.other_actor_id, s.distance + 1, s.path || e.other_actor_id
    FROM search s
    JOIN edge e ON e.actor_id = s.actor_id
    WHERE s.distance < 3
      AND e.other_actor_id <> ALL (s.path)
),
shortest AS (
    SELECT actor_id, min(distance) AS distance
    FROM search
    WHERE actor_id <> 1
    GROUP BY actor_id
)
SELECT distance, count(*) AS actors
FROM shortest
GROUP BY distance
ORDER BY distance;

-- Tarefa 3: caminho mais curto do ator 1 ao ator 200, como lista de nomes,
-- ou resultado vazio se não houver caminho em 5 graus ou menos.
WITH RECURSIVE
edge (actor_id, other_actor_id) AS (
    SELECT fa1.actor_id, fa2.actor_id
    FROM film_actor fa1
    JOIN film_actor fa2 ON fa2.film_id = fa1.film_id AND fa2.actor_id <> fa1.actor_id
    GROUP BY fa1.actor_id, fa2.actor_id
    HAVING count(*) >= 3
),
search (actor_id, distance, path) AS (
    SELECT 1, 0, ARRAY[1]
    UNION ALL
    SELECT e.other_actor_id, s.distance + 1, s.path || e.other_actor_id
    FROM search s
    JOIN edge e ON e.actor_id = s.actor_id
    WHERE s.distance < 5                          -- para ao fim de 5 graus
      AND s.actor_id <> 200                       -- um caminho que já chegou ao destino não continua
      AND e.other_actor_id <> ALL (s.path)
),
best AS (
    -- O mais curto; em caso de empate, o primeiro pela ordem dos IDs, para o resultado ser estável.
    SELECT path
    FROM search
    WHERE actor_id = 200
    ORDER BY distance, path
    LIMIT 1
)
SELECT step.position - 1 AS step, a.actor_id, a.first_name || ' ' || a.last_name AS actor
FROM best
CROSS JOIN LATERAL unnest(best.path) WITH ORDINALITY AS step (actor_id, position)
JOIN actor a ON a.actor_id = step.actor_id
ORDER BY step.position;
