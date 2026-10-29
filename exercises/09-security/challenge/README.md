# Desafio 09 (opcional): a base de dados, não o código, impede a escrita

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `api/app/main.py` | A API do exercício com 3 `GET` novos e o mapeamento dos erros de privilégio para `403` |
| `api/app/clients.py` | Ligações aos três motores. Lê só variáveis de ambiente (sem `.env` por omissão), para que cada instância use só as suas. |
| `api/scripts/setup_mongo.py` | Cria `ex09_app` (`readWrite` em `ex09`) e `ex09_reader` (`read` em `ex09`) |
| `api/scripts/setup_redis.py` | Cria os utilizadores ACL `ex09_app` (`INCR` e `GET` em `counter:*`) e `ex09_reader` (só `GET` em `counter:*`) |
| `api/.env.a.example` | Instância A: os utilizadores que escrevem |
| `api/.env.b.example` | Instância B: os utilizadores só de leitura |
| `api/.env.setup.example` | Credenciais de administração, só para os scripts de setup |
| `api/pyproject.toml`, `api/uv.lock` | Projeto uv |

## Ponto de partida

O exercício 09 feito: base de dados `ex09` com `roles.sql` aplicado (incluindo `ex09_readonly`) e a coleção `notes` criada pelo `setup_mongo.py` do exercício (ver `../exercise/README.md`).

## Como correr

```bash
cd exercises/09-security/challenge/api
cp .env.setup.example .env.setup   # e preencher
cp .env.a.example .env.a           # palavras-passe do exercício
cp .env.b.example .env.b           # ex09_readonly do exercício + as dos leitores de .env.setup
uv sync

# Utilizadores (tarefa 2)
uv run python -m scripts.setup_mongo
uv run python -m scripts.setup_redis

# Duas instâncias do mesmo código; só o ficheiro de ambiente muda (tarefa 3)
uv run uvicorn app.main:app --port 8001 --env-file .env.a &
uv run uvicorn app.main:app --port 8002 --env-file .env.b &
```

Os resultados abaixo foram obtidos com cada instância num contentor `uv` (Python 3.13) na rede do `docker compose`, publicadas em `127.0.0.1:8001` e `127.0.0.1:8002`, com o mesmo código montado nas duas e um `--env-file` diferente.

## Tarefa 1: os `GET` novos

| Endpoint | Motor |
|----------|-------|
| `GET /actors/{actor_id}` | PostgreSQL, `SELECT ... WHERE actor_id = %s`. `404` se não existir. |
| `GET /notes?customer_id=` | MongoDB, `find({"customer_id": <int validado>})` |
| `GET /counters/{name}` | Redis, `GET counter:{name}` com o mesmo padrão de nome. `0` se não existir. |

## Tarefa 2: utilizadores só de leitura

| Motor | Instância A | Instância B |
|-------|-------------|-------------|
| PostgreSQL | `ex09_app`: `SELECT`, `INSERT`, `UPDATE`, `DELETE` | `ex09_readonly`: `SELECT` |
| MongoDB | `ex09_app`: `readWrite` em `ex09` | `ex09_reader`: `read` em `ex09` |
| Redis | `ex09_app`: `~counter:* -@all +incr +get` | `ex09_reader`: `~counter:* -@all +get` |

```
=== setup_mongo
updated user ex09_app on ex09: readWrite on ex09
created user ex09_reader on ex09: read on ex09
=== setup_redis
ACL SETUSER ex09_app reset on >*** ~counter:* resetchannels -@all +incr +get
  INCR counter:setup_probe     -> allowed
  GET counter:setup_probe      -> allowed
  SET counter:setup_probe 1    -> User ex09_app has no permissions to run the 'set' command
  GET other:key                -> User ex09_app has no permissions to access the 'other:key' key
ACL SETUSER ex09_reader reset on >*** ~counter:* resetchannels -@all +get
  INCR counter:setup_probe     -> User ex09_reader has no permissions to run the 'incr' command
  GET counter:setup_probe      -> allowed
  SET counter:setup_probe 1    -> User ex09_reader has no permissions to run the 'set' command
  GET other:key                -> User ex09_reader has no permissions to access the 'other:key' key
```

O `ex09_app` do Redis ganhou `+get` em relação ao exercício, porque a instância A também tem de responder aos `GET`. Os vereditos acima vêm de `ACL DRYRUN`: o Redis diz o que permitiria, sem executar o comando.

## Tarefa 3: duas instâncias, só o ambiente muda

`.env.a` e `.env.b` têm as mesmas 4 variáveis (`DATABASE_URL`, `MONGO_DB`, `MONGO_URL`, `REDIS_URL`), com utilizadores diferentes. O código não tem nenhuma verificação de qual instância é:

```
$ grep -rn -i "8001\|8002\|instance\|readonly\|reader\|ex09_" app/
app/main.py:107:    # INCR explícito: r.incr() do redis-py envia INCRBY, que o ACL de ex09_app não permite.
```

A única ocorrência é um comentário. Ao contrário do exercício, `clients.py` não chama `load_dotenv()`. Assim, a instância B não pode ir buscar por engano as credenciais de escrita a um `.env` que esteja na pasta.

## Tarefa 4: erros de privilégio → `403`

```python
@app.exception_handler(psycopg.errors.InsufficientPrivilege)  # SQLSTATE 42501
async def postgres_forbidden(request, exc): return forbidden("postgres", exc)

@app.exception_handler(OperationFailure)
async def mongo_forbidden(request, exc):
    if exc.code == 13:  # Unauthorized
        return forbidden("mongodb", ...)
    return JSONResponse(status_code=500, content={"detail": "internal server error"})

@app.exception_handler(redis.exceptions.NoPermissionError)  # NOPERM
async def redis_forbidden(request, exc): return forbidden("redis", exc)
```

Só estas três exceções dão `403`, e no MongoDB só o código 13. Qualquer outro erro (ligação recusada, validação do MongoDB, outro `OperationFailure`) continua a ser um `500`. Os endpoints não sabem nada disto: tentam a operação e é o motor que decide.

## Tarefa 5: pedidos e respostas

### Instância A (porta 8001): tudo funciona

```
$ curl -s -i -X GET http://127.0.0.1:8001/actors/1
HTTP/1.1 200 OK
{"actor_id":1,"first_name":"PENELOPE","last_name":"GUINESS"}

$ curl -s -i -X GET http://127.0.0.1:8001/notes?customer_id=1
HTTP/1.1 200 OK
[{"note_id":"6ae34ea51dacd00e8976437b","customer_id":1,"text":"Pediu recomendacoes de ficcao cientifica."}]

$ curl -s -i -X GET http://127.0.0.1:8001/counters/home_page
HTTP/1.1 200 OK
{"name":"home_page","value":2}

$ curl -s -i -X POST http://127.0.0.1:8001/actors -H 'Content-Type: application/json' -d '{"first_name": "GRACE", "last_name": "HOPPER"}'
HTTP/1.1 201 Created
{"actor_id":204}

$ curl -s -i -X POST http://127.0.0.1:8001/notes -H 'Content-Type: application/json' -d '{"customer_id": 1, "text": "Nota escrita pela instancia 8001."}'
HTTP/1.1 201 Created
{"note_id":"6ae356a2e13d6f368777c236"}

$ curl -s -i -X POST http://127.0.0.1:8001/counters/home_page
HTTP/1.1 200 OK
{"name":"home_page","value":3}
```

### Instância B (porta 8002): os `GET` funcionam, os `POST` dão `403`

```
$ curl -s -i -X GET http://127.0.0.1:8002/actors/1
HTTP/1.1 200 OK
{"actor_id":1,"first_name":"PENELOPE","last_name":"GUINESS"}

$ curl -s -i -X GET http://127.0.0.1:8002/notes?customer_id=1
HTTP/1.1 200 OK
[{"note_id":"6ae34ea51dacd00e8976437b","customer_id":1,"text":"Pediu recomendacoes de ficcao cientifica."},{"note_id":"6ae356a2e13d6f368777c236","customer_id":1,"text":"Nota escrita pela instancia 8001."}]

$ curl -s -i -X GET http://127.0.0.1:8002/counters/home_page
HTTP/1.1 200 OK
{"name":"home_page","value":3}

$ curl -s -i -X POST http://127.0.0.1:8002/actors -H 'Content-Type: application/json' -d '{"first_name": "GRACE", "last_name": "HOPPER"}'
HTTP/1.1 403 Forbidden
{"detail":"postgres refused: permission denied for table actor"}

$ curl -s -i -X POST http://127.0.0.1:8002/notes -H 'Content-Type: application/json' -d '{"customer_id": 1, "text": "Nota escrita pela instancia 8002."}'
HTTP/1.1 403 Forbidden
{"detail":"mongodb refused: not authorized on ex09 to execute command { insert: \"notes\", ordered: true, lsid: { id: UUID(\"39eb5a6b-ec24-4c5f-94bc-771bd192a427\") }, $db: \"ex09\" }"}

$ curl -s -i -X POST http://127.0.0.1:8002/counters/home_page
HTTP/1.1 403 Forbidden
{"detail":"redis refused: User ex09_reader has no permissions to run the 'incr' command"}
```

| Pedido | Instância A | Instância B |
|--------|-------------|-------------|
| `GET /actors/1` | 200 | 200 |
| `GET /notes?customer_id=1` | 200 | 200 |
| `GET /counters/home_page` | 200 | 200 |
| `POST /actors` | 201 | **403** (PostgreSQL `42501`) |
| `POST /notes` | 201 | **403** (MongoDB `Unauthorized`, código 13) |
| `POST /counters/home_page` | 200 | **403** (Redis `NOPERM`) |

A instância B lê o que a instância A escreveu (a nota e o contador 3), e cada escrita é recusada pelo motor respetivo, com a mensagem do próprio motor. Não há nenhuma verificação no código: se alguém se esquecesse de uma verificação na aplicação, ou um atacante conseguisse executar código na instância B, as credenciais que ela tem continuavam a não permitir escrever. Isto é privilégio mínimo, aplicado onde os dados estão.
