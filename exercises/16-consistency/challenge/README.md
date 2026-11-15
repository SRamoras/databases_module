# Desafio 16: outbox transacional com falhas do worker e do Redis

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `setup.sql` | A tabela `outbox` do enunciado e um índice parcial nas linhas por processar |
| `rent.py` | Tarefa 1: insere N alugueres; cada aluguer e a sua linha da outbox na mesma transação |
| `worker.py` | Tarefa 2: processa a outbox em lotes de 50 com `FOR UPDATE SKIP LOCKED` |
| `pyproject.toml` | Projeto uv (dependências: `psycopg[binary]`, `redis`) |

A verificação final usa o `verify.py` do exercício (`../exercise/verify.py`).

## Como correr

Ponto de partida: `ex16` e os conjuntos do exercício 16 (`rebuild.py`, `verify.py` com exit 0). A partir da raiz do repositório:

```bash
docker compose exec -T postgres psql -U postgres -d ex16 -v ON_ERROR_STOP=1 < exercises/16-consistency/challenge/setup.sql

rcli() { docker compose exec -T redis redis-cli -a "$REDIS_PASSWORD" --no-auth-warning "$@"; }

# AOF ligado, e appendfsync always (repetir depois de CADA arranque do Redis, antes de o worker escrever)
docker compose -f docker-compose.yml -f docker-compose.redis-aof.yml up -d redis
rcli CONFIG SET appendfsync always
(cd exercises/16-consistency/exercise && uv run python rebuild.py && uv run python verify.py)   # ver "Atenção" abaixo

cd exercises/16-consistency/challenge
uv sync
export DATABASE_URL="postgresql://postgres:<POSTGRES_PASSWORD do .env>@localhost:5432/ex16"
export REDIS_URL="redis://:<REDIS_PASSWORD do .env>@localhost:6379/1"

uv run python worker.py &                 # terminal 1 (WORKER_DELAY=0.01 por omissão: 10 ms por linha)
uv run python rent.py 5000                # terminal 2
kill -9 <pid do worker>                   # a meio de um lote; depois voltar a arrancá-lo
docker compose kill redis                 # a meio de outro lote
docker compose -f docker-compose.yml -f docker-compose.redis-aof.yml up -d redis
rcli CONFIG SET appendfsync always        # o worker espera por isto antes de voltar a escrever

(cd ../exercise && uv run python verify.py; echo "exit $?")

# no fim, voltar à configuração normal do curso (só RDB)
docker compose up -d redis
```

Corri tudo em contentores `uv` na rede do `docker compose`. O `kill -9` do worker foi `docker kill` do contentor dele, que envia `SIGKILL` ao processo.

### Atenção: ligar o AOF apagou as chaves

O comentário no topo do `docker-compose.redis-aof.yml` diz que as chaves ficam ao mudar para AOF, porque estão no volume. Não foi o que aconteceu. Antes de mudar fiz `BGSAVE`, e o Redis tinha 997 chaves na base de dados 1. Depois de recriar o contentor com `--appendonly yes`, tinha 0:

```
$ rcli BGSAVE; rcli INFO keyspace
db0:keys=2,expires=1,...
db1:keys=997,expires=0,...
$ docker compose -f docker-compose.yml -f docker-compose.redis-aof.yml up -d redis
$ rcli INFO keyspace
# Keyspace
$ docker compose logs redis
... * Creating AOF base file appendonly.aof.1.base.rdb on server start
... * Creating AOF incr file appendonly.aof.1.incr.aof on server start
... * Ready to accept connections tcp
```

Com `appendonly yes`, o Redis arranca a partir dos ficheiros AOF e ignora o `dump.rdb`. Como ainda não havia AOF, arrancou vazio e criou um AOF vazio. Aqui não fez mal: as 997 chaves eram derivadas (refeitas com `rebuild.py`, `verify.py` com exit 0) e as 2 da base 0 eram do exercício 15 (filmes vistos, efémeros). Numa instância com dados que não se conseguem reconstruir, o AOF tem de ser ligado com o Redis a correr (`CONFIG SET appendonly yes`), o que reescreve o AOF a partir da memória, e só depois se muda a configuração permanente. O caminho inverso funcionou: ao voltar a `docker compose up -d redis` (sem AOF), o Redis gravou o RDB ao parar e carregou-o ao arrancar (`Done loading RDB, keys loaded: 999`).

## Tarefas 1 e 2

**`rent.py`**: para cada aluguer, numa transação (`with conn.transaction()`), `INSERT INTO rental` (cliente, cópia e funcionário aleatórios, `rental_date = clock_timestamp()`) e `INSERT INTO outbox (customer_id, film_id)`. Ou existem os dois ou nenhum: um aluguer nunca fica sem a linha que avisa o Redis.

**`worker.py`**, em ciclo, cada lote numa transação:

1. `SELECT ... FROM outbox WHERE processed_at IS NULL ORDER BY outbox_id LIMIT 50 FOR UPDATE OF o SKIP LOCKED`, com as categorias de cada filme na mesma query;
2. `SADD customer:{customer_id}:categories <categorias>` por linha (com 10 ms de pausa por linha, para os lotes durarem ~0,5 s e se poder interromper um a meio);
3. `UPDATE outbox SET processed_at = now() WHERE outbox_id = ANY(...)` e `COMMIT`.

O Redis é escrito **antes** do commit. Se o worker morrer depois de escrever no Redis e antes do commit, as linhas continuam por processar (o PostgreSQL desfaz a transação e liberta os locks quando a ligação cai) e outro worker volta a aplicá-las. Na ordem contrária (commit primeiro, Redis depois), uma falha entre os dois deixava linhas marcadas como processadas que nunca chegaram ao Redis.

Se uma escrita no Redis falhar, o bloco `with pg.transaction()` faz rollback (as linhas voltam à fila) e o worker espera até o Redis responder **e** estar com `appendonly yes` e `appendfsync always` (`CONFIG GET`). Só então volta a escrever. Assim o passo "CONFIG SET depois de cada arranque, antes de o worker escrever" não depende de alguém ser rápido: o worker não escreve enquanto o Redis não garantir que cada escrita vai para o disco.

## Tarefa 3: os passos e os logs

| Hora | Passo |
|------|-------|
| 00:40:44 | worker 1 arranca (outbox vazia) |
| 00:40:46 | `rent.py 5000` começa |
| 00:40:49.2 | **`kill -9` do worker 1** (nesse momento: 1.321 linhas na outbox, 1.021 por processar) |
| 00:40:53 | worker 2 arranca |
| 00:40:57.7 | **`docker compose kill redis`** |
| 00:41:02.6 | Redis arranca outra vez com os ficheiros AOF |
| 00:41:03.9 | `CONFIG SET appendfsync always` |
| 00:41:55.9 | outbox: 0 por processar, 5.000 no total |

(As horas da tabela são do meu computador e as dos logs são dos contentores; há uns décimos de segundo de diferença entre os dois relógios.)

`rent.py`:

```
rent: 1000 rentals inserted (4.1s)
rent: 2000 rentals inserted (6.4s)
rent: 3000 rentals inserted (8.7s)
rent: 4000 rentals inserted (10.8s)
rent: 5000 rentals inserted (13.1s)
rent: done, 5000 rentals and 5000 outbox rows
```

### Falha 1: o worker morre a meio de um lote

O fim do log do worker 1. O lote `301..350` foi reclamado e o processo morreu antes do commit (não há linha `committed`):

```
00:40:48.929 [worker pid 10] claimed 50 rows, outbox_id 251..300
00:40:49.203 [worker pid 10]   redis: 25 of 50 rows written (outbox_id up to 275)
00:40:49.492 [worker pid 10] committed outbox_id 251..300
00:40:49.493 [worker pid 10] claimed 50 rows, outbox_id 301..350
                                                    <- kill -9
```

O início do log do worker 2: o primeiro lote que reclama é o mesmo `301..350`. Quando a ligação do worker 1 caiu, o PostgreSQL desfez a transação dele e libertou os locks das linhas, que continuavam com `processed_at` vazio:

```
00:40:53.065 [worker pid 9] started (batch 50, 0.01s per row)
00:40:53.089 [worker pid 9] claimed 50 rows, outbox_id 301..350
00:40:53.349 [worker pid 9]   redis: 25 of 50 rows written (outbox_id up to 325)
00:40:53.626 [worker pid 9] committed outbox_id 301..350
00:40:53.628 [worker pid 9] claimed 50 rows, outbox_id 351..400
```

Algumas das linhas `301..350` já tinham chegado ao Redis antes do kill, e foram aplicadas outra vez.

### Falha 2: o Redis morre a meio de um lote

```
00:40:57.537 [worker pid 9] claimed 50 rows, outbox_id 701..750
00:40:57.797 [worker pid 9]   redis: 25 of 50 rows written (outbox_id up to 725)
00:40:58.080 [worker pid 9] committed outbox_id 701..750
00:40:58.082 [worker pid 9] claimed 50 rows, outbox_id 751..800
00:40:58.147 [worker pid 9] redis error (ConnectionError): batch rolled back, rows go back to the queue
00:40:58.148 [worker pid 9] waiting for redis (ConnectionError)
00:41:07.394 [worker pid 9] redis is back with appendonly yes, appendfsync always (waited 9.2s)
00:41:07.396 [worker pid 9] claimed 50 rows, outbox_id 751..800
00:41:07.656 [worker pid 9]   redis: 25 of 50 rows written (outbox_id up to 775)
00:41:07.938 [worker pid 9] committed outbox_id 751..800
00:41:07.939 [worker pid 9] claimed 50 rows, outbox_id 801..850
```

O Redis morreu depois de o worker escrever algumas linhas do lote `751..800`. O `SADD` seguinte falhou, o lote foi desfeito e o worker esperou. O Redis voltou às 00:41:02.6, mas com `appendfsync everysec` (o valor do ficheiro compose). O worker só voltou a escrever às 00:41:07, depois do `CONFIG SET appendfsync always`. A seguir reclamou outra vez o mesmo lote e terminou-o.

O fim do log:

```
00:41:53.383 [worker pid 9] claimed 50 rows, outbox_id 4951..5000
00:41:53.646 [worker pid 9]   redis: 25 of 50 rows written (outbox_id up to 4975)
00:41:53.927 [worker pid 9] committed outbox_id 4951..5000
00:41:53.928 [worker pid 9] nothing to do, waiting
```

## Tarefa 4: `verify.py` no fim

Sem correr `rebuild.py`:

```
$ uv run python verify.py; echo "exit $?"
checked 999 customers: redis matches postgres
exit 0
```

São 999 clientes e já não 997: os clientes 647 e 978 receberam alugueres aleatórios do `rent.py`, e o worker criou os conjuntos deles.

```
$ psql -tAc "SELECT count(*) FILTER (WHERE processed_at IS NULL) || ' unprocessed, ' || count(*) || ' total' FROM outbox"
0 unprocessed, 5000 total
```

**Todas as 5.000 linhas da outbox foram processadas e o `verify.py` sai com 0**, apesar do `kill -9` do worker e do kill do Redis a meio de lotes.

## Tarefa 5

### Porque é que processar a mesma linha duas vezes é inofensivo aqui

O worker garante "pelo menos uma vez", não "exatamente uma vez": uma linha cujo efeito chegou ao Redis mas cujo commit não chegou ao PostgreSQL é processada outra vez. Aconteceu nas duas falhas (lotes `301..350` e `751..800`).

É inofensivo porque a operação é **idempotente**: `SADD customer:1:categories Action` acrescenta `Action` ao conjunto se não estiver lá e não faz nada se estiver. Aplicar o mesmo `SADD` uma, duas ou dez vezes deixa o mesmo conjunto. O resultado só depende de que linhas foram aplicadas, não de quantas vezes.

Com uma operação que não é idempotente, por exemplo `INCR customer:1:rentals` para contar alugueres, cada repetição contava o aluguer outra vez e o contador ficava acima do valor real. Seria preciso tornar a aplicação de cada linha idempotente:
- **registar no Redis que linhas já foram aplicadas, na mesma operação atómica**: um script Lua (ou `MULTI`/`EXEC`) que faz `SADD outbox:applied <outbox_id>` e só faz o `INCR` se o `SADD` devolver 1 (era nova). Uma repetição encontra o `outbox_id` já aplicado e não incrementa. O conjunto de IDs aplicados tem de ser limpo de vez em quando (por exemplo, guardar só os IDs acima do maior `outbox_id` já confirmado no PostgreSQL);
- **ou escrever um valor absoluto em vez de um incremento**: em vez de `INCR`, `SET customer:1:rentals <count(*) do PostgreSQL>`, recalculado a partir da fonte, como no desafio 14. Repetir dá sempre o mesmo valor.

### Porque é que o resultado depende da persistência do Redis

O worker marca uma linha como processada no PostgreSQL **depois** de o Redis responder `OK` ao `SADD`. A partir desse commit, a outbox considera esse efeito entregue e nunca mais o reenvia. Isto só está certo se o `OK` do Redis significar que a escrita sobrevive a uma falha do Redis.

- **Só RDB**: o Redis guarda um snapshot de tempos a tempos (aqui, no mínimo de 60 em 60 segundos se houver 10.000 alterações, até 1 hora). Um kill do Redis perde tudo o que foi escrito desde o último snapshot. Se o worker processou 2.000 linhas nesse intervalo, o PostgreSQL tem-nas como processadas, mas o Redis volta ao estado antigo sem essas categorias.
- **AOF com `appendfsync everysec`**: o Redis acrescenta cada escrita ao ficheiro, mas só faz `fsync` uma vez por segundo. Com um `kill` do processo (o nosso caso) o sistema operativo ainda tem as escritas em memória e acabam por chegar ao disco. Com uma falha da máquina ou do disco perde-se até cerca de 1 segundo de escritas. São `SADD` com `OK` que o worker já fez commit como processados.
- **`appendfsync always`**: o Redis só responde `OK` depois de a escrita estar no disco (`fsync` em cada comando). Um `OK` é uma escrita que sobrevive. É mais lento, por isso o desafio só o liga aqui.

**Porque é que a outbox sozinha não traz essas escritas de volta.** A outbox só sabe que linhas ainda **não** foram processadas. Uma linha com `processed_at` preenchido nunca mais é lida pelo worker. Se o Redis perder um `SADD` depois de o worker ter feito commit, essa perda é invisível para a outbox: do lado do PostgreSQL está tudo processado, e nada volta a escrever aquelas categorias. Para recuperar seria preciso uma reconciliação de fora: `verify.py` para detetar e `rebuild.py` para refazer tudo a partir das tabelas, não da outbox. A outbox resolve "o PostgreSQL fez commit e o Redis não recebeu"; a persistência resolve "o Redis recebeu e depois perdeu". O resultado só fica certo sem `rebuild.py` com as duas.
