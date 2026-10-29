# Desafio 08 (opcional): Fila de trabalhos com `FOR UPDATE SKIP LOCKED`

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `schema.sql` | As tabelas `job` e `job_result` do enunciado |
| `producer.py` | Insere 10 000 trabalhos `{"n": <número>}` com `COPY`, ou um trabalho lento com `--slow <segundos>` |
| `worker.py` | Processa trabalhos até não haver nenhum pendente, um por transação |
| `check.sql` | Consultas que provam a tarefa 3 |
| `inspect.sql` | Estado do trabalho lento: estado, bloqueio de linha, resultado e ligação do worker (tarefa 4) |
| `pyproject.toml`, `uv.lock` | Projeto uv (dependência: `psycopg[binary]`) |

## Como correr

A partir da raiz do repositório:

```bash
./scripts/create-db.sh ch08 --reset
docker compose exec -T postgres psql -U postgres -d ch08 -v ON_ERROR_STOP=1 < exercises/08-transactions/challenge/schema.sql
docker compose exec -T postgres psql -U postgres -d ch08 -c "CREATE EXTENSION pgrowlocks;"   # só para inspect.sql

cd exercises/08-transactions/challenge
uv sync
export DATABASE_URL="postgresql://postgres:<POSTGRES_PASSWORD do .env>@localhost:5432/ch08"

# Tarefas 1 a 3
uv run producer.py
for w in 1 2 3 4 5 6 7 8; do uv run worker.py $w & done; wait
docker compose exec -T postgres psql -U postgres -d ch08 < check.sql

# Tarefa 4
uv run producer.py --slow 30
uv run worker.py 9 &                 # imprime o seu pid quando começa a dormir
docker compose exec -T postgres psql -U postgres -d ch08 < inspect.sql
kill -9 <pid do worker 9>
docker compose exec -T postgres psql -U postgres -d ch08 < inspect.sql
uv run worker.py 11
docker compose exec -T postgres psql -U postgres -d ch08 < inspect.sql
```

Os resultados abaixo foram obtidos com os workers num contentor `uv` (Python 3.13) na rede do `docker compose`.

## Como o worker funciona

Cada trabalho é uma transação:

```sql
BEGIN;
SELECT job_id, payload FROM job WHERE status = 'pending'
ORDER BY job_id FOR UPDATE SKIP LOCKED LIMIT 1;           -- reclama um trabalho
INSERT INTO job_result (job_id, worker) VALUES (...);     -- processa
-- dorme 1 a 5 ms (ou payload.sleep_seconds no trabalho lento)
UPDATE job SET status = 'done' WHERE job_id = ...;
COMMIT;
```

- `FOR UPDATE` bloqueia a linha do trabalho até ao fim da transação.
- `SKIP LOCKED` faz com que os outros workers **saltem** as linhas bloqueadas, em vez de esperarem por elas. Cada worker reclama assim o primeiro trabalho pendente que ninguém está a processar, sem filas de espera entre workers.
- O resultado, o `status = 'done'` e o desbloqueio acontecem no mesmo `COMMIT`, de forma atómica. Não há nenhum momento em que o trabalho esteja `done` sem resultado, nem com resultado mas ainda `pending` para os outros.
- O worker termina quando o `SELECT` não devolve nenhuma linha: não há trabalhos pendentes que não estejam já reclamados.

## Tarefa 3: 8 workers, cada trabalho uma só vez

```
inserted 10000 jobs
worker 1: processed 1262 jobs
worker 7: processed 1255 jobs
worker 3: processed 1245 jobs
worker 4: processed 1252 jobs
worker 8: processed 1247 jobs
worker 5: processed 1255 jobs
worker 2: processed 1234 jobs
worker 6: processed 1250 jobs
elapsed: 15285 ms
```

A soma dá 10 000. Output de `check.sql`:

```
 results | distinct_jobs | done  | pending
---------+---------------+-------+---------
   10000 |         10000 | 10000 |       0
(1 row)

-- job_id com mais de uma linha em job_result
 job_id | count
--------+-------
(0 rows)

 done_without_result
---------------------
                   0
(1 row)

 worker | jobs
--------+------
      1 | 1262
      2 | 1234
      3 | 1245
      4 | 1252
      5 | 1255
      6 | 1250
      7 | 1255
      8 | 1247
(8 rows)
```

10 000 linhas em `job_result`, 10 000 `job_id` distintos, nenhum `job_id` com mais de uma linha, e nenhum trabalho pendente. O trabalho ficou repartido por igual pelos 8 workers.

## Tarefa 4: matar o worker a meio de um trabalho

### 1. Um trabalho lento e um worker que o reclama

```
$ uv run producer.py --slow 30
inserted slow job 10001 (30 s)

$ uv run worker.py 9 &
worker 9 (pid 220): job 10001 sleeps 30 s
```

### 2. Enquanto o worker 9 dorme (`inspect.sql`)

```
 job_id |            payload            | status
--------+-------------------------------+---------
  10001 | {"n": 0, "sleep_seconds": 30} | pending

 locked_row | locker |     modes      |  pids
------------+--------+----------------+--------
 (109,1)    |  51808 | {"For Update"} | {9004}

 job_id | worker | processed_at
--------+--------+--------------
(0 rows)

 pid  | application_name |        state        |                       last_query
------+------------------+---------------------+---------------------------------------------------------
 9004 | worker-9         | idle in transaction | INSERT INTO job_result (job_id, worker) VALUES ($1, $2)
```

- **Trabalho:** continua `pending`, porque o `UPDATE` ainda não aconteceu.
- **Linha do trabalho:** tem um bloqueio `For Update` da transação 51808, do processo servidor 9004.
- **Ligação:** a `worker-9` está `idle in transaction`. O worker não está a falar com a base de dados, está a dormir no meio de uma transação aberta.
- **`job_result`:** o worker já inseriu a linha, mas ela não aparece, porque ainda não houve commit e nenhuma outra transação a vê.

Um worker que arranque agora ignora o trabalho, por causa do `SKIP LOCKED`:

```
$ uv run worker.py 10
worker 10: processed 0 jobs
```

### 3. `kill -9` do worker 9

```
$ kill -9 220
kill -9 220: ok
pid 220 gone
```

`kill -9` (SIGKILL) não deixa o processo fazer nada antes de morrer: não há `ROLLBACK`, `close()` nem blocos `finally`. O sistema operativo fecha o socket, e o PostgreSQL vê a ligação cair a meio de uma transação. Log do servidor:

```
[9004] LOG:  unexpected EOF on client connection with an open transaction
```

### 4. Logo a seguir (`inspect.sql`)

```
 job_id |            payload            | status
--------+-------------------------------+---------
  10001 | {"n": 0, "sleep_seconds": 30} | pending

 locked_row | locker | modes | pids
------------+--------+-------+------
(0 rows)

 job_id | worker | processed_at
--------+--------+--------------
(0 rows)

 pid | application_name | state | last_query
-----+------------------+-------+------------
(0 rows)
```

| | Enquanto o worker 9 dormia | Depois do `kill -9` |
|---|---|---|
| `job.status` | `pending` | `pending` |
| Bloqueio da linha | `For Update`, pid 9004 | nenhum |
| Linha em `job_result` | inserida mas invisível (sem commit) | desapareceu: a transação foi desfeita |
| Ligação `worker-9` | `idle in transaction` | terminada |

O servidor desfez a transação aberta (*rollback*). O `INSERT` em `job_result` nunca chegou a existir para mais ninguém, e o bloqueio libertou-se. O trabalho ficou exatamente como estava antes de o worker 9 o reclamar.

### 5. Outro worker processa-o

```
$ uv run worker.py 11
worker 11 (pid 257): job 10001 sleeps 30 s
worker 11: processed 1 jobs
took 30 s
```

No fim:

```
 job_id |            payload            | status
--------+-------------------------------+--------
  10001 | {"n": 0, "sleep_seconds": 30} | done

 job_id | worker |         processed_at
--------+--------+-------------------------------
  10001 |     11 | 2026-10-29 14:14:58.436905+00

 results | distinct_jobs | pending
---------+---------------+---------
   10001 |         10001 |       0
```

O trabalho 10001 foi processado pelo worker 11 e tem uma única linha em `job_result`. Os 10 001 trabalhos foram processados exatamente uma vez cada.

## E se o processamento enviasse um email em vez de inserir uma linha?

Inserir em `job_result` faz parte da mesma transação que o `UPDATE ... 'done'`. Por isso o efeito do processamento e o "está feito" são confirmados ou desfeitos juntos, e o resultado é *exactly once*.

Um email é um efeito **fora** da base de dados, que nenhum `ROLLBACK` desfaz. Se o worker enviar o email e morrer antes do `COMMIT`, o trabalho volta a `pending`, outro worker reclama-o, e **o email é enviado outra vez**. A fila passa a garantir *at least once*: cada email sai pelo menos uma vez, mas pode sair duas. Trocar a ordem (commit primeiro, email depois) dá o problema contrário: se o worker morrer entre o commit e o envio, o trabalho fica `done` e o email nunca sai (*at most once*).

Não há forma de tornar uma transação da base de dados e um envio de email atómicos. As soluções práticas aceitam *at least once* e tornam o envio **idempotente**:
- **Chave de idempotência:** guardar uma chave única por trabalho (por exemplo `job_id`) e passá-la ao serviço de email, se ele a suportar. O serviço ignora um segundo envio com a mesma chave.
- **Estado intermédio:** marcar o trabalho como `sending` num commit, enviar, e marcar `done` noutro commit. Um trabalho encontrado em `sending` depois de uma falha é verificado (o email saiu?) antes de ser reenviado.
- **Duplicados toleráveis:** para emails, muitas vezes basta aceitar um duplicado ocasional.
