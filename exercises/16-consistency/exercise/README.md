# Exercício 16: Redis como dados derivados (rebuild, verify e persistência)

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `categories.py` | O que `rebuild.py` e `verify.py` partilham: o nome da chave e a query única que lê os conjuntos esperados do PostgreSQL |
| `rebuild.py` | Tarefa 1: recria todos os `customer:{customer_id}:categories` com 1 query e 1 pipeline |
| `verify.py` | Tarefa 3: compara o Redis com o PostgreSQL; termina com 1 se houver diferenças, 0 se não |
| `pyproject.toml` | Projeto uv (dependências: `redis`, `psycopg[binary]`) |

## Como correr

A partir da raiz do repositório:

```bash
./scripts/create-db.sh ex16 --pagila --reset

cd exercises/16-consistency/exercise
uv sync
export DATABASE_URL="postgresql://postgres:<POSTGRES_PASSWORD do .env>@localhost:5432/ex16"
export REDIS_URL="redis://:<REDIS_PASSWORD do .env>@localhost:6379/1"     # base de dados lógica 1
# opcional: se existir, os dois scripts leem o PostgreSQL com READONLY_DATABASE_URL

uv run python rebuild.py
uv run python verify.py; echo "exit $?"
```

`redis-cli` no contentor, sempre na base de dados 1 (`-n 1`):

```bash
rcli() { docker compose exec -T redis redis-cli -a "$REDIS_PASSWORD" --no-auth-warning -n 1 "$@"; }
rcli FLUSHDB
rcli --scan --pattern 'customer:*:categories' | wc -l
```

## Tarefa 1: `rebuild.py`

- **Uma query** (`categories.EXPECTED_SQL`): `rental` → `inventory` → `film_category` → `category`, com `array_agg(DISTINCT c.name ORDER BY c.name)` agrupado por `customer_id`. Devolve uma linha por cliente com alugueres, com as categorias sem repetições (um filme pode ter várias, e o cliente pode ter alugado muitos filmes da mesma).
- **Um pipeline**: para cada cliente, `DEL customer:{id}:categories:rebuild`, `SADD` de todas as categorias nessa chave temporária e `RENAME` para a chave real. No mesmo pipeline, `DEL` das chaves de clientes que não deviam ter conjunto (encontradas com `SCAN` antes).
- **Porque a chave temporária**: o `RENAME` substitui a chave real num só passo. Um leitor vê o conjunto antigo ou o novo, nunca um conjunto vazio ou a meio do `SADD`. Se o rebuild morrer a meio, as chaves reais ficam com o valor anterior (no pior caso sobra uma chave `:rebuild`, que o próximo rebuild apaga antes de a usar).
- O pipeline é `transaction=False`: uma só ida e volta ao Redis, mas sem `MULTI`/`EXEC` à volta dos 2.991 comandos. A atomicidade de cada conjunto vem do `RENAME`. Um `MULTI` com tudo bloquearia o Redis durante o rebuild inteiro, e não é preciso que todos os conjuntos mudem ao mesmo tempo, só que cada um mude de uma vez.

## Tarefa 2: `FLUSHDB`, rebuild e contagem com `SCAN`

```
$ redis-cli -n 1 FLUSHDB
OK
$ uv run python rebuild.py
rebuilt 997 sets, deleted 0 stale set(s), 1 query, 1 pipeline of 2991 commands, 0.15s
$ redis-cli -n 1 --scan --pattern 'customer:*:categories' | wc -l
997
$ redis-cli -n 1 DBSIZE
997
$ redis-cli -n 1 SCARD customer:1:categories
16
```

**997 conjuntos** (os clientes 647 e 978 não têm alugueres). `redis-cli --scan` usa `SCAN` por baixo: percorre as chaves aos bocados, com um cursor, sem bloquear o Redis como o `KEYS *` faria. 2.991 comandos = 997 × 3 (`DEL`, `SADD`, `RENAME`).

## Tarefa 3: `verify.py`

Lê os conjuntos esperados com a mesma query, lê os 997 conjuntos do Redis com um pipeline de `SMEMBERS`, compara tamanho e membros, e depois procura com `SCAN` chaves `customer:*:categories` de clientes que não deviam ter conjunto.

```
$ uv run python verify.py
checked 997 customers: redis matches postgres
exit 0

$ redis-cli -n 1 SREM customer:1:categories Action
1
$ uv run python verify.py
customer:1:categories: redis 15 members, postgres 16; missing in redis ['Action']
checked 997 customers: 1 difference(s)
exit 1

$ redis-cli -n 1 SADD customer:647:categories Fake
1
$ uv run python verify.py
customer:1:categories: redis 15 members, postgres 16; missing in redis ['Action']
customer:647:categories: should not exist (customer has no rentals), has ['Fake']
checked 997 customers: 2 difference(s)
exit 1

$ uv run python rebuild.py
rebuilt 997 sets, deleted 1 stale set(s), 1 query, 1 pipeline of 2992 commands, 0.15s
$ uv run python verify.py
checked 997 customers: redis matches postgres
exit 0
```

Deteta as duas alterações (exit 1) e passa depois do rebuild (exit 0). O segundo rebuild apagou o conjunto do cliente 647 (`deleted 1 stale set(s)`): um rebuild que só escrevesse os conjuntos esperados deixaria lá o `Fake`.

## Tarefa 4: classificação das chaves dos exercícios 15 e 16

| Chave | Classe | O que se perde se o Redis a perder | Como volta |
|-------|--------|------------------------------------|------------|
| `customer:{id}:viewed` (filmes vistos, ex. 15) | **Efémero** | A lista dos últimos 20 filmes vistos de cada cliente. Não existe em mais lado nenhum | Não volta. Recomeça vazia e enche-se à medida que os clientes veem filmes. É aceitável porque é só uma conveniência de navegação ("vistos recentemente"): nenhuma decisão de negócio nem dinheiro depende dela, e já expira sozinha ao fim de 30 dias |
| `cache:film:{id}` (cache, ex. 15) | **Derivado** | Nada que não exista no PostgreSQL. Só o trabalho de o ter ido buscar | Sozinha: o próximo `get_film` é um miss, lê o PostgreSQL e volta a guardar (cache-aside). Durante uns minutos há mais leituras no PostgreSQL |
| `lock:refresh:monthly_revenue` (lock, ex. 15) | **Efémero** | O facto de um processo estar a fazer o refresh nesse momento | Não precisa de voltar: dura no máximo 60 s. Se o Redis perder o lock durante um refresh, um segundo processo pode fazer outro refresh ao mesmo tempo. É inofensivo, porque `REFRESH MATERIALIZED VIEW CONCURRENTLY` é idempotente e o PostgreSQL serializa os dois. Se fosse um trabalho com efeitos não repetíveis (enviar emails), o lock do Redis não chegava |
| `ratelimit:{id}:{minuto}` (rate limit, ex. 15) | **Efémero** | Os contadores do minuto atual | Recomeçam a 0 no minuto seguinte (ou logo). No pior caso um cliente faz até 20 pedidos nesse minuto em vez de 10. Aceitável para um limite de abuso; não seria para uma quota paga |
| `customer:{id}:categories` (categorias, ex. 16) | **Derivado** | Nada: são calculados a partir de `rental`, `inventory` e `film_category` | `rebuild.py` (cerca de 0,15 s), e `verify.py` confirma. Enquanto não houver rebuild, quem lê não encontra os conjuntos |

Nenhuma chave é **fonte da verdade**: tudo o que não se pode perder (clientes, alugueres, pagamentos, filmes) está no PostgreSQL.

## Tarefa 5: configuração do Redis

Configuração atual (o `docker-compose.yml` do curso, sem alterações):

```
$ redis-cli CONFIG GET appendonly appendfsync maxmemory maxmemory-policy save
appendonly        no
appendfsync       everysec
maxmemory         0
maxmemory-policy  noeviction
save              3600 1 300 100 60 10000
```

**A minha escolha, para uma instância com estas chaves:**

```
appendonly no
save 3600 1 300 100 60 10000      # RDB, como já está
maxmemory 256mb
maxmemory-policy volatile-lru
```

**Persistência: só RDB, sem AOF.** Pela tabela da tarefa 4, nada aqui é fonte da verdade: os dados derivados reconstroem-se (cache sozinha, categorias com `rebuild.py` em 0,15 s) e os efémeros podem perder-se por definição. O AOF existe para não perder escritas que não se conseguem recuperar de outro lado, e aqui não há nenhuma. O AOF custaria escritas em disco a cada segundo e reinícios mais lentos, sem proteger nada que valha a pena. Mantenho os snapshots RDB porque são baratos e evitam começar completamente a frio depois de um reinício planeado: os filmes vistos e a cache voltam (no máximo com minutos de atraso), em vez de recomeçar do zero. Se o RDB estiver atrasado, as categorias podem estar desatualizadas, por isso o procedimento depois de um reinício é correr `rebuild.py` (ou pelo menos `verify.py`), e não confiar no snapshot.

**`maxmemory 256mb`.** Sem limite (`maxmemory 0`), uma cache ou um conjunto de chaves que cresce sem controlo pode usar toda a memória da máquina e o sistema operativo mata o Redis (e possivelmente outros processos). Com limite, o Redis decide o que fazer quando chega lá. Hoje usa 2,3 MB; 256 MB dá folga para crescer.

**`maxmemory-policy volatile-lru`, e o compromisso.** A política aplica-se à instância inteira, não a cada chave, e as chaves daqui pedem coisas diferentes:
- para a **cache** (`cache:film:*`), o certo seria `allkeys-lru`: quando falta memória, deita-se fora o que é menos usado, e um miss só custa uma leitura ao PostgreSQL;
- para os **conjuntos de categorias**, despejar um conjunto em silêncio é mau: quem o lê recebe um conjunto vazio, que parece "este cliente não alugou nada" e não "falta este dado". O `verify.py` deteta-o, mas só quando corre;
- para os **locks** e o **rate limit**, despejar é perigoso: um lock despejado deixa entrar um segundo processo, um contador despejado deixa passar pedidos a mais. Com `noeviction` o Redis recusa as escritas novas (erro `OOM`), o que é melhor do que perder estas chaves sem aviso, mas também recusa a cache, e a aplicação passa a ter erros.

`volatile-lru` só despeja chaves **com TTL**. Aqui isso é a cache (300 s), os filmes vistos (30 dias), o rate limit e os locks (60 s). Os conjuntos de categorias não têm TTL, por isso nunca são despejados. É um compromisso: os locks e os contadores também têm TTL e podiam ser despejados, embora o LRU prefira as chaves usadas há mais tempo, e um lock ou um contador do minuto atual são sempre recentes. Se a memória acabar só com chaves sem TTL, o Redis passa a comportar-se como `noeviction` e recusa escritas.

**Quando usaria duas instâncias.** Quando os dados pedem políticas incompatíveis e o compromisso não chega:
- uma instância **cache**, com `maxmemory` e `allkeys-lru`, sem persistência: pode despejar o que quiser, e perdê-la toda não faz mal;
- uma instância para **estado que não se pode despejar** (locks, rate limit, filas, e dados derivados que se leem como verdade, como as categorias), com `noeviction` e, se houver alguma coisa que não se consiga reconstruir (por exemplo uma fila de trabalhos), AOF com `appendfsync everysec`.

Assim uma cache que cresce não pode fazer desaparecer um lock, e a instância do estado não perde desempenho com escritas da cache no AOF. O custo é mais um serviço para gerir e duas ligações na aplicação. Faz sentido quando a cache é grande ou quando a fila ou os locks são críticos. Para o tamanho destes exercícios uma instância com `volatile-lru` chega.

**AOF neste repositório.** O `docker-compose.redis-aof.yml` liga o AOF (`--appendonly yes --appendfsync everysec`). Como diz o aviso no topo desse ficheiro, aplicá-lo (`docker compose -f docker-compose.yml -f docker-compose.redis-aof.yml up -d redis`) recria o contentor do Redis, que fica em baixo alguns segundos para todos os projetos que o usam (as chaves ficam, porque estão no volume `redis_data`), e volta-se ao normal com `docker compose up -d redis`. Pela justificação acima, este exercício não precisa dele; o desafio 16 sim.
