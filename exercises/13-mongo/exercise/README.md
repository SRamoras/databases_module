# Exercício 13: Documentos, CRUD, validação e índices em MongoDB

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `load.py` | Tarefa 1: lê a Pagila e escreve `films`, `customers` e `rentals` em `pagila_docs` |
| `operations.js` | Tarefa 2: as 8 operações |
| `validation.js` | Tarefa 3: `$jsonSchema` em `films` e as duas inserções rejeitadas |
| `index.js` | Tarefa 4: `explain("executionStats")` antes e depois do índice em `actors.actor_id` |
| `pyproject.toml`, `uv.lock` | Projeto uv (`pymongo`, `psycopg[binary]`) |
| `.env.example` | `DATABASE_URL` e `MONGO_URL` |

## Como correr

A partir da raiz do repositório, com os motores a correr (`docker compose up -d`):

```bash
./scripts/create-db.sh ex13 --pagila --reset
cp exercises/13-mongo/exercise/.env.example exercises/13-mongo/exercise/.env   # e pôr as palavras-passe

# 1. Carregar (pode correr-se as vezes que se quiser)
(cd exercises/13-mongo/exercise && uv run --env-file .env python load.py)

# 2-4. Os scripts de mongosh, dentro do contentor
mongo() {
  docker compose exec -T mongo mongosh -u root -p "$MONGO_ROOT_PASSWORD" \
    --authenticationDatabase admin --quiet pagila_docs "$@"
}
set -a; source .env; set +a
mongo --eval "$(cat exercises/13-mongo/exercise/operations.js)"
mongo --eval "$(cat exercises/13-mongo/exercise/validation.js)"
mongo --eval "$(cat exercises/13-mongo/exercise/index.js)"
```

As operações 6, 7 e 8 alteram dados. Antes de as repetir, ou antes do exercício 14, apagar o filme de teste e carregar outra vez:

```bash
mongo --eval 'db.films.deleteOne({_id: 1001})'
(cd exercises/13-mongo/exercise && uv run --env-file .env python load.py)
```

## Tarefa 1: `load.py`

Lê com 4 consultas SQL (filmes com as categorias e os atores agregados em `array_agg` / `json_agg`, clientes com cidade e país, os 10 alugueres mais recentes de cada cliente com `row_number()`, e os alugueres com a soma dos pagamentos) e escreve com `bulk_write` de `ReplaceOne({"_id": ...}, doc, upsert=True)`. O dinheiro vai como `Decimal128` (a partir do `Decimal` do psycopg, nunca de `float`) e as datas como datas BSON.

Output:

```text
films: 1000
customers: 999
rentals: 51805
films: 1000 documentos
customers: 999 documentos
rentals: 51805 documentos
```

**Correr duas vezes deixa os mesmos documentos.** Os `_id` são os IDs da Pagila e cada documento é substituído inteiro, por isso a segunda corrida não cria duplicados nem deixa campos antigos. Confirmei com o `dbHash` das três coleções, que é igual depois da primeira e da segunda corrida:

```text
{"customers":"97e6ec84d35a33b8faad54b206084198","films":"b274b58c3788ee09cb5b49ff311babe5","rentals":"c27f206869b63cf4901270fef12bca48"}
{"customers":"97e6ec84d35a33b8faad54b206084198","films":"b274b58c3788ee09cb5b49ff311babe5","rentals":"c27f206869b63cf4901270fef12bca48"}
```

Os documentos do filme 1, do cliente 1 e do aluguer 87420 são iguais aos do enunciado.

### Porque embutir ou referenciar

- **Atores e categorias embutidos em `films`.** Lêem-se sempre com o filme (a ficha de um filme mostra o elenco e as categorias). São poucos e o número não cresce: no máximo 15 atores e 3 categorias por filme. Quase não mudam. Guardo só o que se mostra (`actor_id` e nome), e o `actor_id` continua a permitir pesquisar por ator (operação 2, com índice multikey). A duplicação do nome de um ator em vários filmes é aceitável porque os nomes praticamente nunca mudam.
- **Só os 10 alugueres mais recentes em `customers`.** A página de um cliente mostra a atividade recente, e assim lê-se com um único documento. Embutir o histórico todo seria um array que cresce sem limite: cada aluguer novo aumentava o documento, que se lia e reescrevia por inteiro, e no fim chegaria aos 16 MB. Com 10 o tamanho tem limite (`$push` com `$slice`, operação 7). `rental_count` evita contar o histórico para mostrar o total.
- **O histórico completo em `rentals`.** Cada aluguer é um documento à parte, que referencia o cliente e o filme pelo ID. Cresce sem afetar o tamanho dos outros documentos, lê-se sozinho ou por cliente, e serve para relatórios (exercício 14). Leva uma cópia do título e das categorias para os relatórios não precisarem de `$lookup`.

## Tarefa 2: `operations.js`

Resultados numa base acabada de carregar:

| # | Operação | Resultado | Esperado |
|---|----------|-----------|----------|
| 1 | `countDocuments({ rating: "PG-13", length: { $gt: 120 } })` | 118 | 118 |
| 2 | `countDocuments({ "actors.actor_id": 1 })` | 19 | 19 |
| 3 | `countDocuments({ categories: "Horror", rental_rate: NumberDecimal("0.99") })` | 43 | 43 |
| 4 | `countDocuments({ recent_rentals: { $elemMatch: { return_date: null } } })` | 56 | 56 |
| 5 | `findOne({ _id: 1 }, { _id: 0, first_name: 1, last_name: 1, "recent_rentals.title": 1 })` | 1 documento, 10 títulos | 1 documento com 10 títulos |
| 6 | `updateMany({ rating: "NC-17", length: { $lt: 60 } }, { $inc: { rental_rate: NumberDecimal("0.50") } })` | `matched 21, modified 21` | 21 modificados |
| 7 | `updateOne({ _id: 1 }, { $push: { recent_rentals: { $each: [novo], $position: 0, $slice: 10 } } })` | `size 10`, primeiro `90001` | 10 itens, o primeiro é o novo |
| 8 | `updateOne({ _id: 1001 }, { $setOnInsert: { title: "TEST FILM" } }, { upsert: true })` × 2 | 1.ª: `upserted 1`; 2.ª: `matched 1, modified 0` | idem |

Output:

```text
--- 1. PG-13 e length > 120
118
--- 2. ator 1
19
--- 3. Horror e rental_rate 0.99
43
--- 4. clientes com aluguer aberto em recent_rentals
56
--- 5. projeção do cliente 1
{"first_name":"MARY","last_name":"SMITH","recent_rentals":[{"title":"FELLOWSHIP AUTUMN"},{"title":"FUGITIVE MAGUIRE"},{"title":"CHASING FIGHT"},{"title":"GLEAMING JAWBREAKER"},{"title":"SECRET GROUNDHOG"},{"title":"MULAN MOON"},{"title":"BRAVEHEART HUMAN"},{"title":"SPLENDOR PATTON"},{"title":"DRACULA CRYSTAL"},{"title":"SHAKESPEARE SADDLE"}]}
--- 5. número de títulos
10
--- 6. updateMany $inc
{"matched":21,"modified":21}
--- 7. $push com $each, $position e $slice
{"modified":1,"size":10,"first":90001,"last":74068}
--- 8. upsert, execução 1
{"matched":0,"modified":0,"upserted":1}
--- 8. upsert, execução 2
{"matched":1,"modified":0,"upserted":0}
```

Notas:

- **3:** o valor tem de ser `NumberDecimal("0.99")`. O número `0.99` é um double e não é igual ao `Decimal128` guardado.
- **4:** `$elemMatch` aplica a condição a cada elemento do array. `return_date: null` encontra elementos em que o campo é `null` (ou não existe).
- **7:** o array tinha 10 alugueres. `$position: 0` põe o novo à cabeça e `$slice: 10` corta o mais antigo, por isso o último passa a ser o 9.º de antes (74068).
- **8:** na segunda execução o documento já existe: o filtro encontra-o e `$setOnInsert` não faz nada, por isso `modified` é 0.

## Tarefa 3: validação

`validation.js` aplica com `collMod` (`validationLevel: "strict"`, `validationAction: "error"`): `title` string; `rating` em `["G", "PG", "PG-13", "R", "NC-17"]`; `length` `int` entre 1 e 999; `rental_rate` `decimal`; `categories` array de strings; `actors` array de objetos com `actor_id` `int` e `name` string. Também pus estes campos como `required`.

O `load.py` continua a correr com a validação ligada (os 1000 filmes passam). O pymongo grava `int` do Python como `int` BSON e `Decimal128` como `decimal`, por isso os tipos coincidem:

```text
films: 1000
customers: 999
rentals: 51805
```

As duas inserções inválidas (um filme válido em que só muda um campo):

```text
collMod: {"ok":1}

rating: "XXX": rejeitado, MongoServerError (code 121): Document failed validation
[{"operatorName":"properties","propertiesNotSatisfied":[{"propertyName":"rating","details":[{"operatorName":"enum","specifiedAs":{"enum":["G","PG","PG-13","R","NC-17"]},"reason":"value was not found in enum","consideredValue":"XXX"}]}]}]

length: "long": rejeitado, MongoServerError (code 121): Document failed validation
[{"operatorName":"properties","propertiesNotSatisfied":[{"propertyName":"length","details":[{"operatorName":"bsonType","specifiedAs":{"bsonType":"int"},"reason":"type did not match","consideredValue":"long","consideredType":"string"}]}]}]
```

O filme de teste 1001 da operação 8 (só com `title`) não cumpre o esquema. O `collMod` não verifica documentos que já existem; com `strict`, qualquer `update` a esse documento passaria a ser validado e falharia.

## Tarefa 4: índice multikey

Output de `index.js`:

```text
Antes do índice
  stage:             COLLSCAN
  totalKeysExamined: 0
  totalDocsExamined: 1000
  nReturned:         19
  executionTimeMillis: 0

createIndex: actors.actor_id_1

Depois do índice
  stage:             FETCH <- IXSCAN (actors.actor_id_1, isMultiKey: true)
  totalKeysExamined: 19
  totalDocsExamined: 19
  nReturned:         19
  executionTimeMillis: 0
```

| | `stage` | `totalDocsExamined` | `nReturned` |
|---|---------|---------------------|-------------|
| Antes | `COLLSCAN` | 1000 | 19 |
| Depois | `IXSCAN` + `FETCH` | 19 | 19 |

Sem índice, o MongoDB lê os 1000 filmes para devolver 19. Com o índice só lê os 19 que devolve. O índice é multikey porque `actors` é um array: cada filme tem uma entrada no índice por cada ator. Com 1000 documentos as duas versões levam menos de 1 ms, mas o `COLLSCAN` cresce com o tamanho da coleção e o `IXSCAN` só com o número de resultados.
