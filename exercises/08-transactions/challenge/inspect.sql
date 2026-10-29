-- Estado do trabalho lento (o último inserido), do seu bloqueio e do seu resultado.
SELECT job_id, payload, status FROM job WHERE payload ? 'sleep_seconds';

-- Bloqueios de linha em job (pgrowlocks lê-os diretamente das páginas da tabela).
SELECT locked_row, locker, modes, pids FROM pgrowlocks('job');

-- Resultados visíveis do trabalho lento (uma linha ainda não confirmada não aparece).
SELECT r.* FROM job_result r JOIN job j USING (job_id) WHERE j.payload ? 'sleep_seconds';

-- Ligações dos workers.
SELECT pid, application_name, state, left(query, 60) AS last_query
FROM pg_stat_activity WHERE application_name LIKE 'worker-%' ORDER BY application_name;
