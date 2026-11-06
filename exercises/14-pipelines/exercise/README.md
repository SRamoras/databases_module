# Exercício 14: Pipelines de agregação, backup e restauro em MongoDB

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `pipelines.js` | Tarefas 1 a 4: os quatro pipelines, cada um com o número de documentos e os primeiros resultados |
| `backup_mongo.sh` | Tarefa 5: `mongodump` de `pagila_docs` para `backups/` |
| `restore_mongo.sh` | Tarefa 5: restaura o arquivo mais recente para `pagila_docs_restored` e compara as contagens |

## Como correr

A partir da raiz do repositório, com os motores a correr (`docker compose up -d`). As coleções `films` e `rentals` têm de estar como o `load.py` do exercício 13 as deixa (ver o README desse exercício para as carregar outra vez):

```bash
set -a; source .env; set +a
docker compose exec -T mongo mongosh -u root -p "$MONGO_ROOT_PASSWORD" --authenticationDatabase admin \
    --quiet pagila_docs --eval "$(cat exercises/14-pipelines/exercise/pipelines.js)"

exercises/14-pipelines/exercise/backup_mongo.sh
exercises/14-pipelines/exercise/restore_mongo.sh
```

Os scripts de backup e restauro podem correr de qualquer pasta: mudam para a raiz do repositório e leem o `.env`. Os arquivos ficam em `backups/`, que está no `.gitignore`.

## Tarefa 1: receita por categoria por mês em 2025

```js
db.rentals.aggregate([
  { $match: { rental_date: { $gte: ISODate("2025-01-01T00:00:00Z"), $lt: ISODate("2026-01-01T00:00:00Z") } } },
  { $unwind: "$categories" },
  { $group: {
      _id: { category: "$categories",
             month: { $dateToString: { date: "$rental_date", format: "%Y-%m", timezone: "UTC" } } },
      revenue: { $sum: "$amount" } } },
  { $project: { _id: 0, category: "$_id.category", month: "$_id.month", revenue: 1 } },
  { $sort: { category: 1, month: 1 } }
])
```

O `$match` vem primeiro, para os estágios seguintes só receberem os alugueres de 2025. O `$unwind` das categorias faz um aluguer de um filme com 3 categorias contar para as 3, tal como o `JOIN` com `film_category` no SQL. `amount` é `Decimal128`, por isso a soma é exata.

**192 documentos** (16 categorias × 12 meses):

```text
{"revenue":{"$numberDecimal":"333.87"},"category":"Action","month":"2025-01"}
{"revenue":{"$numberDecimal":"342.98"},"category":"Action","month":"2025-02"}
{"revenue":{"$numberDecimal":"385.83"},"category":"Action","month":"2025-03"}
{"revenue":{"$numberDecimal":"349.91"},"category":"Action","month":"2025-04"}
{"revenue":{"$numberDecimal":"380.76"},"category":"Action","month":"2025-05"}
```

### Porque é que Action em janeiro de 2025 dá 333.87 aqui e 314.94 no exercício 05

As duas consultas somam os mesmos pagamentos, mas põem-nos em meses diferentes:

- No exercício 05 o mês é o do **pagamento** (`payment.payment_date`).
- Aqui o mês é o do **aluguer** (`rentals.rental_date`). O `amount` de cada documento é a soma dos pagamentos desse aluguer, feitos quando forem.

Um pagamento não acontece sempre no mês do aluguer. Confirmei com SQL na Pagila, só para Action:

| | Valor | Pagamentos |
|---|---:|---:|
| Receita de janeiro por `payment_date` (exercício 05) | 314.94 | |
| − pagos em janeiro, de alugueres de dezembro de 2024 ou antes | −27.90 | 10 |
| + de alugueres de janeiro, pagos em fevereiro ou depois | +46.83 | 17 |
| = Receita de janeiro por `rental_date` (este exercício) | **333.87** | |

Nenhum dos valores está errado. Respondem a perguntas diferentes: o do exercício 05 é o dinheiro que entrou em janeiro (o que interessa à contabilidade); este é quanto renderam os alugueres feitos em janeiro (o que interessa para avaliar a procura). Este também ainda pode mudar: se um aluguer de janeiro for pago mais tarde, o valor de janeiro sobe.

## Tarefa 2: o ator com mais filmes em cada categoria

```js
db.films.aggregate([
  { $unwind: "$categories" },
  { $unwind: "$actors" },
  { $group: { _id: { category: "$categories", actor_id: "$actors.actor_id" },
              name: { $first: "$actors.name" }, films: { $sum: 1 } } },
  { $setWindowFields: { partitionBy: "$_id.category", sortBy: { films: -1 },
                        output: { rank: { $rank: {} } } } },
  { $match: { rank: 1 } },
  { $sort: { "_id.actor_id": 1 } },
  { $group: { _id: "$_id.category", films: { $first: "$films" },
              actors: { $push: { actor_id: "$_id.actor_id", name: "$name" } } } },
  { $project: { _id: 0, category: "$_id", films: 1, actors: 1 } },
  { $sort: { category: 1 } }
])
```

`$rank` dá o lugar 1 a todos os atores empatados no máximo, por isso `rank: 1` inclui os empates. Fiz o `$sort` por `actor_id` antes do último `$group` para os atores de cada categoria ficarem por ordem.

**16 documentos, 30 atores no total:**

```text
{"films":10,"actors":[{"actor_id":65,"name":"ANGELA HUDSON"},{"actor_id":181,"name":"MATTHEW CARREY"}],"category":"Action"}
{"films":10,"actors":[{"actor_id":13,"name":"UMA WOOD"},{"actor_id":150,"name":"JAYNE NOLTE"}],"category":"Animation"}
{"films":9,"actors":[{"actor_id":105,"name":"SIDNEY CROWE"},{"actor_id":133,"name":"RICHARD PENN"},{"actor_id":139,"name":"EWAN GOODING"}],"category":"Children"}
{"films":10,"actors":[{"actor_id":94,"name":"KENNETH TORN"}],"category":"Classics"}
{"films":11,"actors":[{"actor_id":107,"name":"GINA DEGENERES"}],"category":"Comedy"}
{"films":11,"actors":[{"actor_id":50,"name":"NATALIE HOPKINS"},{"actor_id":102,"name":"WALTER TORN"},{"actor_id":150,"name":"JAYNE NOLTE"}],"category":"Documentary"}
{"films":10,"actors":[{"actor_id":129,"name":"DARYL CRAWFORD"}],"category":"Drama"}
{"films":10,"actors":[{"actor_id":45,"name":"REESE KILMER"},{"actor_id":144,"name":"ANGELA WITHERSPOON"}],"category":"Family"}
{"films":9,"actors":[{"actor_id":14,"name":"VIVIEN BERGEN"},{"actor_id":32,"name":"TIM HACKMAN"},{"actor_id":65,"name":"ANGELA HUDSON"},{"actor_id":81,"name":"SCARLETT DAMON"},{"actor_id":107,"name":"GINA DEGENERES"},{"actor_id":143,"name":"RIVER DEAN"},{"actor_id":191,"name":"GREGORY GOODING"}],"category":"Foreign"}
{"films":11,"actors":[{"actor_id":136,"name":"ED MANSFIELD"}],"category":"Games"}
{"films":10,"actors":[{"actor_id":106,"name":"GROUCHO DUNST"},{"actor_id":108,"name":"WARREN NOLTE"}],"category":"Horror"}
{"films":11,"actors":[{"actor_id":127,"name":"KEVIN GARLAND"}],"category":"Music"}
{"films":11,"actors":[{"actor_id":76,"name":"ANGELINA ASTAIRE"}],"category":"New"}
{"films":10,"actors":[{"actor_id":155,"name":"IAN TANDY"}],"category":"Sci-Fi"}
{"films":13,"actors":[{"actor_id":198,"name":"MARY KEITEL"}],"category":"Sports"}
{"films":11,"actors":[{"actor_id":198,"name":"MARY KEITEL"}],"category":"Travel"}
atores no total: 30
```

## Tarefa 3: distribuição das durações

```js
db.films.aggregate([
  { $bucket: { groupBy: "$length", boundaries: [0, 60, 90, 120, 150, 186],
               output: { films: { $sum: 1 } } } }
])
```

**5 documentos.** Cada intervalo inclui o limite inferior e exclui o superior (`[0, 60)`, ..., `[150, 186)`). O último limite é 186 para incluir os filmes de 185 minutos.

```text
{"_id":0,"films":96}
{"_id":60,"films":224}
{"_id":90,"films":214}
{"_id":120,"films":216}
{"_id":150,"films":250}
```

Não pus `default`: todas as durações estão entre 46 e 185, e se um filme ficasse fora dos limites o `$bucket` dava erro em vez de o esconder num grupo "outros".

## Tarefa 4: `$facet`

```js
db.films.aggregate([
  { $facet: {
      totals: [
        { $group: { _id: null, films: { $sum: 1 }, avg_rental_rate: { $avg: "$rental_rate" } } },
        { $project: { _id: 0, films: 1, avg_rental_rate: { $round: ["$avg_rental_rate", 2] } } } ],
      by_rating: [
        { $group: { _id: "$rating", films: { $sum: 1 } } },
        { $set: { order: { $indexOfArray: [["G", "PG", "PG-13", "R", "NC-17"], "$_id"] } } },
        { $sort: { order: 1 } },
        { $project: { _id: 0, rating: "$_id", films: 1 } } ],
      longest: [
        { $sort: { length: -1, title: 1 } },
        { $limit: 5 },
        { $project: { _id: 0, title: 1, length: 1 } } ]
  } }
])
```

**1 documento:**

```json
{
  "totals": [{ "films": 1000, "avg_rental_rate": { "$numberDecimal": "2.98" } }],
  "by_rating": [
    { "films": 178, "rating": "G" },
    { "films": 194, "rating": "PG" },
    { "films": 223, "rating": "PG-13" },
    { "films": 195, "rating": "R" },
    { "films": 210, "rating": "NC-17" }
  ],
  "longest": [
    { "title": "CHICAGO NORTH", "length": 185 },
    { "title": "CONTROL ANTHEM", "length": 185 },
    { "title": "DARN FORRESTER", "length": 185 },
    { "title": "GANGS PRIDE", "length": 185 },
    { "title": "HOME PITY", "length": 185 }
  ]
}
```

Há 10 filmes com 185 minutos; o `title` no `$sort` desempata, e os 5 primeiros por ordem alfabética são os esperados. As classificações seguem a ordem G → NC-17 (`$indexOfArray`) em vez da ordem alfabética.

## Tarefa 5: backup e restauro

`backup_mongo.sh` corre `mongodump --db pagila_docs --archive --gzip` dentro do contentor e grava o arquivo em `backups/mongo_pagila_docs_<data>_<hora>.archive.gz`. Pus também a hora no nome, para dois backups no mesmo dia não se sobreporem.

```text
Backup: backups/mongo_pagila_docs_2026-11-06_031331.archive.gz (2.4M)
```

`restore_mongo.sh` escolhe o arquivo mais recente (`ls -t`), restaura-o com `--nsFrom 'pagila_docs.*' --nsTo 'pagila_docs_restored.*' --drop` (a base original não é tocada, e correr outra vez substitui as coleções restauradas) e compara o número de documentos de cada coleção nas duas bases. Termina com código 1 se alguma contagem for diferente.

Output de `restore_mongo.sh` (sem os timestamps do `mongorestore`):

```text
A restaurar backups/mongo_pagila_docs_2026-11-06_031331.archive.gz para pagila_docs_restored
preparing collections to restore from
reading metadata for `pagila_docs_restored.films` from `archive on stdin`
reading metadata for `pagila_docs_restored.customers` from `archive on stdin`
reading metadata for `pagila_docs_restored.rentals` from `archive on stdin`
dropping collection `pagila_docs_restored.films` before restoring
restoring `pagila_docs_restored.films` from `archive on stdin`
dropping collection `pagila_docs_restored.customers` before restoring
restoring `pagila_docs_restored.customers` from `archive on stdin`
finished restoring `pagila_docs_restored.films` (1000 documents, 0 failures)
finished restoring `pagila_docs_restored.customers` (999 documents, 0 failures)
dropping collection `pagila_docs_restored.rentals` before restoring
restoring `pagila_docs_restored.rentals` from `archive on stdin`
finished restoring `pagila_docs_restored.rentals` (51805 documents, 0 failures)
restoring indexes for collection `pagila_docs_restored.films` from metadata
index: &idx.IndexDocument{Options:bson.M{"name":"actors.actor_id_1", "v":2}, Key:bson.D{bson.E{Key:"actors.actor_id", Value:1}}, PartialFilterExpression:(*bson.D)(nil)}
no indexes to restore for collection `pagila_docs_restored.customers`
no indexes to restore for collection `pagila_docs_restored.rentals`
53804 document(s) restored successfully. 0 document(s) failed to restore.

coleção      pagila_docs  pagila_docs_restored
customers            999                   999
films               1000                  1000
rentals            51805                 51805

OK: contagens iguais
```

O arquivo também leva os índices (o `actors.actor_id_1` do exercício 13) e as opções das coleções, incluindo a validação `$jsonSchema` de `films`, por isso a base restaurada fica igual à original e não só com os mesmos documentos.
