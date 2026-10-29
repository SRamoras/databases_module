-- Provas da tarefa 3: cada trabalho processado exatamente uma vez.

-- 10 000 resultados, 10 000 trabalhos distintos, nenhum pendente.
SELECT (SELECT count(*) FROM job_result)                 AS results,
       (SELECT count(DISTINCT job_id) FROM job_result)   AS distinct_jobs,
       (SELECT count(*) FROM job WHERE status = 'done')  AS done,
       (SELECT count(*) FROM job WHERE status = 'pending') AS pending;

-- Nenhum job_id com mais de uma linha (deve devolver 0 linhas).
SELECT job_id, count(*) FROM job_result GROUP BY job_id HAVING count(*) > 1;

-- Nenhum trabalho done sem resultado, nem resultado de um trabalho que não está done.
SELECT count(*) AS done_without_result
FROM job j WHERE j.status = 'done' AND NOT EXISTS (SELECT 1 FROM job_result r WHERE r.job_id = j.job_id);

-- Distribuição pelos workers.
SELECT worker, count(*) AS jobs FROM job_result GROUP BY worker ORDER BY worker;
