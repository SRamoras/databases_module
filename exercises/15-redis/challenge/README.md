# Desafio 15: rate limit com janela deslizante

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `rate_limit.py` | `allow_request_fixed(customer_id, now)`, `allow_request_sliding(customer_id, now)` (script Lua) e, só para o teste da atomicidade, `allow_request_sliding_not_atomic` |
| `tests/test_rate_limit.py` | Os testes das tarefas 3 e 4, e mais dois |
| `pyproject.toml` | Projeto uv (dependências: `redis`, `pytest`) |

## Como correr

```bash
cd exercises/15-redis/challenge
uv sync
export REDIS_URL="redis://:<REDIS_PASSWORD do .env>@localhost:6379/0"
uv run pytest -v -s
```

Os testes usam o cliente 4242 e apagam as chaves `ratelimit:*:4242*` antes e depois de cada teste.

## As duas funções

**Janela fixa** (`allow_request_fixed`): a função do exercício 15, com o tempo como argumento. Um contador por cliente por minuto do calendário, `ratelimit:fixed:{customer_id}:{int(now // 60)}`, com `INCR` e `EXPIRE 60 NX`.

**Janela deslizante** (`allow_request_sliding`): um sorted set por cliente, `ratelimit:sliding:{customer_id}`, com um membro por pedido aceite e a hora do pedido como score. Um script Lua faz, num só passo:

```lua
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)   -- esquece os pedidos com mais de 60 s
if redis.call('ZCARD', key) >= limit then                    -- já há 10 nos últimos 60 s?
    return 0                                                 -- recusa (e não regista)
end
redis.call('ZADD', key, now, member)                         -- regista este pedido
redis.call('EXPIRE', key, math.ceil(window))                 -- a chave desaparece 60 s depois do último
return 1
```

- A janela é "os últimos 60 segundos antes deste pedido", seja qual for o minuto do relógio.
- **Membros únicos:** o membro é `"<now>:<uuid>"`. Se fosse só a hora, dois pedidos no mesmo instante seriam o mesmo membro: o segundo `ZADD` só atualizava o score do primeiro, e o conjunto contava 1 em vez de 2 (o limite deixava passar mais pedidos). O teste de concorrência manda os 30 pedidos com o mesmo `now` precisamente para isto.
- Pedidos recusados não são registados, por isso um cliente que insiste não prolonga o seu próprio bloqueio.

## `uv run pytest -v -s`

```
============================= test session starts ==============================
platform linux -- Python 3.13.11, pytest-9.2.0, pluggy-1.7.0
collecting ... collected 5 items

tests/test_rate_limit.py::test_fixed_window_accepts_20_across_the_minute_boundary
fixed:   20 accepted of 20 -> [True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True]
PASSED
tests/test_rate_limit.py::test_sliding_window_accepts_only_10_in_any_60_seconds
sliding: 10 accepted of 20 -> [True, True, True, True, True, True, True, True, True, True, False, False, False, False, False, False, False, False, False, False]
PASSED
tests/test_rate_limit.py::test_sliding_window_accepts_again_after_60_seconds PASSED
tests/test_rate_limit.py::test_sliding_window_under_concurrency_accepts_exactly_10
concurrent sliding: 30 requests, 10 accepted, 10 members in the sorted set
PASSED
tests/test_rate_limit.py::test_check_then_add_in_separate_commands_breaks_the_limit
not atomic: A True, B True, 11 requests in the window (limit 10)
PASSED

============================== 5 passed in 0.67s ===============================
```

| Teste | O que mostra |
|-------|--------------|
| `test_fixed_window_accepts_20_across_the_minute_boundary` | Tarefa 3: 10 pedidos aos 59,0–59,9 s de um minuto e 10 aos 0,0–0,9 s do seguinte. A janela fixa aceita **20** em menos de 2 segundos: os primeiros 10 contam no contador de um minuto, os outros 10 num contador novo |
| `test_sliding_window_accepts_only_10_in_any_60_seconds` | Tarefa 3: os mesmos 20 pedidos. A janela deslizante aceita **10**: aos 0,0 s do minuto seguinte, os 10 pedidos de há 1 segundo ainda estão nos últimos 60 s |
| `test_sliding_window_accepts_again_after_60_seconds` | Um pedido volta a ser aceite quando o mais antigo sai da janela (60 s depois dele), e só esse |
| `test_sliding_window_under_concurrency_accepts_exactly_10` | Tarefa 4: 10 threads, sincronizadas com uma `Barrier`, mandam 3 pedidos cada (30) no mesmo instante. Exatamente **10** aceites e 10 membros no sorted set |
| `test_check_then_add_in_separate_commands_breaks_the_limit` | Porque tem de ser atómico (abaixo) |

## Porque é que a verificação e o registo têm de ser atómicos

A janela deslizante é "conta, e se houver espaço, regista". Se forem comandos separados enviados pelo cliente (`ZREMRANGEBYSCORE`, `ZCARD`, depois `ZADD`), entre o `ZCARD` e o `ZADD` podem correr comandos de outros clientes. Com 9 pedidos na janela, dois pedidos simultâneos fazem ambos `ZCARD` e veem 9 ("há espaço"), e ambos fazem `ZADD`. Ficam 11 na janela, com limite 10. Com mais clientes ao mesmo tempo o excesso é maior: todos os que contarem antes de o primeiro registar passam.

O último teste força exatamente essa intercalação com a versão não atómica: o cliente B corre inteiro entre o `ZCARD` e o `ZADD` do cliente A. Resultado: **A e B aceites, 11 pedidos na janela**. É um *check-then-act*, a mesma corrida do lost update no PostgreSQL.

Um `MULTI`/`EXEC` (pipeline) não resolve: os comandos de uma transação Redis são enviados todos antes de qualquer resultado voltar, por isso não se pode decidir o `ZADD` com base no resultado do `ZCARD` dentro dela. Com `WATCH` resolvia-se, mas com repetições sempre que outro pedido do mesmo cliente chegasse no meio, exatamente o caso que interessa. O script Lua corre inteiro dentro do Redis, que executa um comando (ou script) de cada vez: entre o `ZCARD` e o `ZADD` não corre mais nada. Por isso o teste de concorrência dá sempre exatamente 10.

A janela fixa não precisa de script porque não verifica antes de escrever: o `INCR` incrementa e devolve o valor novo num só comando atómico, e a decisão é tomada sobre esse valor. Cada pedido recebe um número diferente (1, 2, ..., 30), e só os 10 primeiros passam.
