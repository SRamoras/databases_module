# Exercício 15: quatro padrões Redis sobre o Pagila

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `setup.sql` | A vista materializada `monthly_revenue` (a do exercício 06) e o índice único que o `REFRESH ... CONCURRENTLY` precisa |
| `patterns.py` | As funções: `record_view`, `recent_views`, `get_film`, `update_film_rate`, `acquire_lock`, `unlock` (script Lua), `allow_request` |
| `demo.py` | Demonstrações das tarefas 1, 2 e 4, e de que um lock não é libertado por quem não o tem |
| `refresh.py` | Tarefa 3: refresh da vista com o lock `lock:refresh:monthly_revenue` |
| `pyproject.toml` | Projeto uv (dependências: `redis`, `psycopg[binary]`) |

## Como correr

A partir da raiz do repositório:

```bash
./scripts/create-db.sh ex15 --pagila --reset
docker compose exec -T postgres psql -U postgres -d ex15 -v ON_ERROR_STOP=1 < exercises/15-redis/exercise/setup.sql

cd exercises/15-redis/exercise
uv sync
export DATABASE_URL="postgresql://postgres:<POSTGRES_PASSWORD do .env>@localhost:5432/ex15"
export REDIS_URL="redis://:<REDIS_PASSWORD do .env>@localhost:6379/0"

uv run python demo.py                                            # demora até 2 minutos (tarefa 4)
uv run python refresh.py & uv run python refresh.py & wait       # tarefa 3
```

`demo.py` pode ser repetido: apaga as chaves que usa antes de começar e repõe a taxa do filme 1 em 0.99 no PostgreSQL.

## Output de `demo.py`

```
=== 1. Recently viewed films
customer 1 viewed films 1 to 25
recent_views(1) = [25, 24, 23, 22, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6]
ZCARD customer:1:viewed = 20
customer 1 viewed film 10 again
recent_views(1) = [10, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 9, 8, 7, 6]
film 10 appears 1 time(s); ZCARD = 20
TTL customer:1:viewed = 2592000 seconds (30 days = 2592000)

=== 2. Cache-aside for film 1
get_film(1), first : miss -> {'title': 'ACADEMY DINOSAUR', 'rating': 'PG', 'length': 86, 'rental_rate': '0.99'}  (TTL 300s)
get_film(1), second: hit  -> {'title': 'ACADEMY DINOSAUR', 'rating': 'PG', 'length': 86, 'rental_rate': '0.99'}  (TTL 300s)
update_film_rate(1, 1.99): PostgreSQL updated, EXISTS cache:film:1 = 0
get_film(1), third : miss -> {'title': 'ACADEMY DINOSAUR', 'rating': 'PG', 'length': 86, 'rental_rate': '1.99'}  (TTL 300s)
get_film(1), fourth: hit  -> {'title': 'ACADEMY DINOSAUR', 'rating': 'PG', 'length': 86, 'rental_rate': '1.99'}  (TTL 300s)

=== 3. The lock is never released by a process that does not hold it
A acquires lock:demo: True
B acquires lock:demo: False  (A holds it)
... A is slow; its lock expires after 1 second
B acquires lock:demo: True
A releases with its old token: False  (lock still held by B: True)
B releases with its token:     True  (EXISTS lock:demo = 0)

=== 4. Rate limit: 10 requests per customer per minute
(waiting 35s for a new minute to start)
12 calls for customer 1 in minute 29911714: [True, True, True, True, True, True, True, True, True, True, False, False]
True: 10, False: 2
GET ratelimit:1:29911714 = 12, TTL 60s
(waiting 60s for the next minute)
call in minute 29911715: True
GET ratelimit:1:29911715 = 1
```

### 1. Filmes vistos recentemente

`record_view` corre três comandos num `MULTI`/`EXEC` (pipeline com `transaction=True`):

```
ZADD customer:1:viewed <agora> <film_id>      -- se o filme já lá está, só atualiza o score
ZREMRANGEBYRANK customer:1:viewed 0 -21       -- remove tudo menos os 20 scores mais altos
EXPIRE customer:1:viewed 2592000              -- 30 dias depois desta visualização
```

`recent_views` é `ZRANGE customer:1:viewed 0 -1 REV`. Depois dos filmes 1 a 25 ficam os 20 mais recentes, do 25 ao 6. Ver o filme 10 outra vez não o duplica, porque um sorted set tem membros únicos: o `ZADD` só lhe muda o score para o momento atual e ele passa para a frente. O `EXPIRE` em cada visualização faz com que a chave expire 30 dias depois da **última**.

### 2. Cache-aside

- `get_film` lê `cache:film:1`. Na falta (miss) lê o PostgreSQL e guarda o JSON com `SET ... EX 300`.
- `update_film_rate` atualiza primeiro o PostgreSQL (a fonte da verdade) e faz commit, e só depois apaga a chave. Se fosse ao contrário, um `get_film` entre o `DEL` e o commit voltava a pôr na cache o valor antigo, que ficava lá até expirar.
- O valor monetário vai como texto (`"0.99"`), para não passar por `float`.

O primeiro `get_film` é miss, o segundo hit, depois da atualização o terceiro é miss e já traz 1.99.

### 3. Lock

Explicado com `refresh.py` abaixo. A secção 3 do `demo.py` mostra a regra de libertação: A tem o lock, demora mais do que a expiração e o lock passa para B. Quando A acaba e tenta libertar, o script Lua compara o token guardado com o de A, vê que é diferente e **não apaga** (`False`). O lock continua a ser de B. Só B o liberta.

### 4. Rate limit

`allow_request(customer_id)` faz `INCR ratelimit:{customer_id}:{minuto}` e `EXPIRE ... 60 NX` num `MULTI`/`EXEC`, e aceita se o contador for ≤ 10. O minuto é `int(time() // 60)`, por isso a chave muda sozinha quando começa um minuto novo, e a antiga desaparece com o `EXPIRE`. O `NX` define a expiração só quando o contador é criado. A demonstração espera pelo início de um minuto para as 12 chamadas caírem todas na mesma janela: 10 `True` e 2 `False`. No minuto seguinte, a primeira chamada é `True` (contador novo, 1).

## Output de `refresh.py` (dois processos ao mesmo tempo)

```
$ uv run python refresh.py & uv run python refresh.py & wait
00:35:00.550 [pid 39] acquired lock:refresh:monthly_revenue with token e36b36a4...
00:35:00.551 [pid 38] skipped: lock:refresh:monthly_revenue is held by token e36b36a4..., TTL 60s
00:35:00.605 [pid 39] refreshed monthly_revenue in 0.05s
00:35:00.605 [pid 39] holding the lock for 5 more seconds
00:35:05.606 [pid 39] released the lock: True
```

Os dois processos fazem `SET lock:refresh:monthly_revenue <uuid> NX EX 60` ao mesmo tempo. O Redis executa um comando de cada vez, por isso só o primeiro recebe `OK`; o segundo recebe `nil` e desiste sem fazer o refresh. O processo 39 faz o refresh, espera 5 segundos com o lock e liberta-o com o script Lua:

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
```

O `GET` e o `DEL` correm dentro do Redis como um só passo. Com `GET` e `DEL` enviados pelo Python em dois comandos, o lock podia expirar e ser apanhado por outro processo entre os dois, e o `DEL` apagava o lock do outro. O `EX 60` garante que, se o processo morrer com o lock, ele desaparece sozinho ao fim de 60 segundos e o próximo refresh não fica bloqueado para sempre.

## As chaves

| Chave | Tipo | TTL | Para quê |
|-------|------|-----|----------|
| `customer:{customer_id}:viewed` | sorted set (membro: `film_id`, score: hora da visualização em segundos) | 30 dias, renovado a cada visualização | Os 20 filmes vistos mais recentemente por um cliente |
| `cache:film:{film_id}` | string (JSON com `title`, `rating`, `length`, `rental_rate`) | 300 s | Cache-aside dos dados de um filme; apagada quando a taxa muda |
| `lock:refresh:monthly_revenue` | string (token aleatório do dono) | 60 s | Garante que só um processo faz o refresh da vista de cada vez |
| `lock:demo` | string (token) | 1 s / 60 s | Só na demonstração da libertação do lock |
| `ratelimit:{customer_id}:{minute}` | string com um inteiro (`INCR`) | 60 s, definido quando é criada | Pedidos de um cliente num minuto (`minute` = segundos desde 1970 / 60) |
