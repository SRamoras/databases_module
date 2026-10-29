# Exercício 08: Lost updates, deadlocks e write skew

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `setup.sql` | A preparação do enunciado: coluna `balance` em `customer` e 14 funcionários temporários na loja 1 (fica com 20 ativos) |
| [`lost_update.md`](lost_update.md) | Tarefas 1 e 2: o lost update e as duas correções, sessão a sessão |
| [`deadlock.md`](deadlock.md) | Tarefa 3: o deadlock, a mensagem de erro explicada linha a linha e como o prevenir |
| `write_skew.py` | Tarefa 4: 20 threads, uma por funcionário ativo da loja 1 |
| `pyproject.toml`, `uv.lock` | Projeto uv (dependência: `psycopg[binary]`) |

## Como correr

A partir da raiz do repositório:

```bash
./scripts/create-db.sh ex08 --pagila --reset
docker compose exec -T postgres psql -U postgres -d ex08 -v ON_ERROR_STOP=1 < exercises/08-transactions/exercise/setup.sql
```

Para as tarefas 1 a 3, abrir duas sessões (`docker compose exec postgres psql -U postgres -d ex08`) e seguir as tabelas de `lost_update.md` e `deadlock.md`.

Tarefa 4:

```bash
cd exercises/08-transactions/exercise
uv sync
export DATABASE_URL="postgresql://postgres:<POSTGRES_PASSWORD do .env>@localhost:5432/ex08"

uv run write_skew.py read-committed
docker compose exec -T postgres psql -U postgres -d ex08 -c "SELECT count(*) FROM staff WHERE store_id = 1 AND active;"

docker compose exec -T postgres psql -U postgres -d ex08 -c "UPDATE staff SET active = true WHERE store_id = 1;"

uv run write_skew.py serializable
docker compose exec -T postgres psql -U postgres -d ex08 -c "SELECT count(*) FROM staff WHERE store_id = 1 AND active;"
```

## Resumo das tarefas 1 a 3

| Tarefa | Resultado |
|--------|-----------|
| 1. Lost update | Saldo final **90** (devia ser 80) |
| 2. `UPDATE` atómico | Saldo final **80** |
| 2. `SELECT ... FOR UPDATE` | Saldo final **80** |
| 3. Deadlock | `ERROR: deadlock detected` na sessão A, que é desfeita; B termina |

Os detalhes, com os comandos de cada sessão por ordem e o output, estão em [`lost_update.md`](lost_update.md) e [`deadlock.md`](deadlock.md).

## Tarefa 4: write skew

Regra: cada loja mantém pelo menos um funcionário ativo. Cada uma das 20 threads tem a sua ligação e corre uma transação:

1. conta os funcionários ativos da loja 1;
2. espera na `Barrier(20)` até todas terem contado (só na primeira tentativa);
3. se a contagem for maior que 1, desativa-se a si própria;
4. `COMMIT`.

Com `SERIALIZABLE`, uma transação que falhe com SQLSTATE `40001` (`psycopg.errors.SerializationFailure`) é repetida desde o início, sem a barreira.

### 4.1 `READ COMMITTED`

```
isolation: read-committed
active staff in store 1 before: 20
  staff 1509: attempt 1, saw 20 active, deactivated
  staff 1506: attempt 1, saw 20 active, deactivated
  staff 36: attempt 1, saw 20 active, deactivated
  staff 1505: attempt 1, saw 20 active, deactivated
  staff 1508: attempt 1, saw 20 active, deactivated
  staff 1504: attempt 1, saw 20 active, deactivated
  staff 1511: attempt 1, saw 20 active, deactivated
  staff 1507: attempt 1, saw 20 active, deactivated
  staff 1436: attempt 1, saw 20 active, deactivated
  staff 1502: attempt 1, saw 20 active, deactivated
  staff 1471: attempt 1, saw 20 active, deactivated
  staff 1421: attempt 1, saw 20 active, deactivated
  staff 27: attempt 1, saw 20 active, deactivated
  staff 1513: attempt 1, saw 20 active, deactivated
  staff 6: attempt 1, saw 20 active, deactivated
  staff 1512: attempt 1, saw 20 active, deactivated
  staff 1503: attempt 1, saw 20 active, deactivated
  staff 1501: attempt 1, saw 20 active, deactivated
  staff 1510: attempt 1, saw 20 active, deactivated
  staff 1514: attempt 1, saw 20 active, deactivated
serialization failures (retried): 0
active staff in store 1 after: 0
```

```
 active_store_1
----------------
              0
```

**A regra foi violada: a loja 1 ficou com 0 funcionários ativos.**

### 4.2 Reposição

```
UPDATE staff SET active = true WHERE store_id = 1;
UPDATE 20
```

### 4.3 `SERIALIZABLE` com repetição

O output tem 228 linhas (uma por tentativa). Estas são as primeiras, as 19 tentativas que chegaram ao fim e as últimas:

```
isolation: serializable
active staff in store 1 before: 20
  staff 1436: attempt 1, serialization failure (40001), retrying
  staff 1502: attempt 1, serialization failure (40001), retrying
  staff 1508: attempt 1, serialization failure (40001), retrying
  ... (17 das 20 primeiras tentativas falham)
  staff 1511: attempt 1, saw 20 active, deactivated
  staff 1502: attempt 2, saw 19 active, deactivated
  staff 1510: attempt 2, saw 18 active, deactivated
  staff 1504: attempt 3, saw 17 active, deactivated
  staff 1507: attempt 4, saw 16 active, deactivated
  staff 27: attempt 5, saw 15 active, deactivated
  staff 1421: attempt 6, saw 14 active, deactivated
  staff 1508: attempt 7, saw 13 active, deactivated
  staff 1509: attempt 8, saw 12 active, deactivated
  staff 1501: attempt 9, saw 11 active, deactivated
  staff 1506: attempt 9, saw 10 active, deactivated
  staff 1436: attempt 11, saw 9 active, deactivated
  staff 1513: attempt 10, saw 8 active, deactivated
  staff 1471: attempt 13, saw 7 active, deactivated
  staff 1512: attempt 14, saw 6 active, deactivated
  staff 1505: attempt 17, saw 5 active, deactivated
  staff 36: attempt 18, saw 4 active, deactivated
  staff 1503: attempt 21, saw 3 active, deactivated
  staff 6: attempt 30, saw 2 active, deactivated
  ...
  staff 1514: attempt 37, serialization failure (40001), retrying
  staff 1514: attempt 38, saw 1 active, stayed active
serialization failures (retried): 208
active staff in store 1 after: 1
```

```
 active_store_1
----------------
              1
```

**Exatamente 1 funcionário fica ativo (o 1514).** Cada transação que chegou ao fim viu uma contagem diferente (20, 19, 18, ..., 2) e a última viu 1 e não se desativou. O resultado é o mesmo que se as 20 transações tivessem corrido uma de cada vez.

## Porque é que `READ COMMITTED` quebra a regra e `SERIALIZABLE` não

**`READ COMMITTED`.** As 20 transações contam ao mesmo tempo e todas veem 20 ativos, porque a barreira garante que ainda ninguém escreveu. Cada uma conclui "há mais do que 1, posso sair" e desativa **a sua própria linha**. Como as linhas são todas diferentes, não há nenhum conflito de escrita: nenhum `UPDATE` espera por outro e nenhum bloqueio de linha é disputado. Cada transação está certa sozinha, mas juntas violam a regra, porque a decisão de cada uma se baseou numa leitura que as escritas das outras tornaram falsa. Isto é o *write skew*. O `FOR UPDATE` do lost update não resolve, porque o problema não está numa linha que duas transações escrevem, mas num conjunto de linhas que todas leem (a contagem) e que cada uma altera numa linha diferente.

**`SERIALIZABLE`.** O PostgreSQL usa *Serializable Snapshot Isolation*: regista o que cada transação leu (neste caso, as linhas ativas da loja 1) e o que escreveu. Quando a transação X leu dados que a transação Y depois alterou, e Y leu dados que X alterou, há um ciclo de dependências leitura-escrita. Nenhuma ordem em série das duas daria o mesmo resultado. O motor deteta esse padrão e faz falhar uma delas com `40001 could not serialize access`. Só uma das 20 primeiras transações conseguiu fazer commit. As outras falharam e repetiram desde o início, já sem a barreira, e a nova contagem já via a desativação confirmada. O processo repete-se até a última repetição ver 1 ativo e não fazer nada.

O preço é visível: 208 repetições para 20 transações. Com muita disputa, `SERIALIZABLE` é correto mas caro. A aplicação tem de estar preparada para repetir transações. Uma alternativa para esta regra específica era serializar à mão, bloqueando a linha da loja (`SELECT ... FROM store WHERE store_id = 1 FOR UPDATE`) antes de contar.
