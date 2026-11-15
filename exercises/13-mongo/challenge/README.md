# Desafio 13: bucket pattern para o histórico de alugueres

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `buckets.py` | `create_indexes`, `add_rental`, o carregamento de `rental_buckets` e `rental_history`, o teste de concorrência e as comparações |
| `pyproject.toml` | Projeto uv (dependências: `pymongo`, `psycopg[binary]`) |

## Como correr

Precisa da coleção `rentals` do exercício 13 (`exercises/13-mongo/exercise/load.py`).

```bash
cd exercises/13-mongo/challenge
uv sync
export MONGO_URL="mongodb://root:<MONGO_ROOT_PASSWORD do .env>@localhost:27017/?authSource=admin"

uv run python buckets.py load                       # tarefas 3 e 4
uv run python buckets.py concurrency                # tarefa 2: 8 threads, o mesmo cliente
uv run python buckets.py compare                    # tarefa 5: cliente 380
uv run python buckets.py large                      # a mesma comparação com 20.000 alugueres
```

## Tarefa 1: o desenho

```js
// rental_buckets: no máximo 50 alugueres de um cliente por documento
// (o segundo balde do cliente 380, com o primeiro aluguer)
{
  _id: ObjectId('6af8fc0834fe35474ff44928'),
  customer_id: 380,
  seq: 2,                 // 1, 2, 3... por cliente; o maior é o mais recente
  count: 47,              // número de elementos de rentals (evita $size no filtro)
  rentals: [              // por ordem de rental_date (o mais antigo primeiro)
    { rental_id: 55135, film_id: 305, title: 'FATAL HAUNTED',
      rental_date: ISODate('2023-01-07T20:45:28.153Z'), return_date: ISODate('2023-01-11T15:17:16.859Z'),
      amount: Decimal128('2.99') },
    ...
  ]
}
```

Índices:

| Índice | Para quê |
|--------|----------|
| `{customer_id: 1, seq: 1}` único (`customer_seq`) | Ler os baldes de um cliente por ordem; nunca dois baldes com o mesmo número |
| `{customer_id: 1}` único **parcial** com `partialFilterExpression: {count: {$lt: 50}}` (`one_open_bucket`) | No máximo **um balde aberto** por cliente. Um balde cheio (50) sai do índice e deixa de contar |

Cada aluguer do balde guarda o que o histórico mostra (`rental_id`, `film_id`, `title`, datas, `amount`). `customer_id` está no balde, não em cada aluguer.

## Tarefa 2: `add_rental`

```python
last = buckets.find_one({"customer_id": customer_id}, {"seq": 1}, sort=[("seq", DESCENDING)])
next_seq = last["seq"] + 1 if last else 1
buckets.update_one(
    {"customer_id": customer_id, "count": {"$lt": 50}},
    {"$push": {"rentals": rental}, "$inc": {"count": 1}, "$setOnInsert": {"seq": next_seq}},
    upsert=True,
)
# DuplicateKeyError -> repetir desde o início (no máximo 5 vezes)
```

A escrita é um único `updateOne` com `upsert: true` e um filtro em `count`:
- se o cliente tem um balde aberto (`count < 50`), o filtro encontra-o, `$push` acrescenta o aluguer e `$inc` sobe o `count`;
- se não tem (nenhum balde, ou o último está cheio), o upsert cria um balde novo com `customer_id` (vem da igualdade no filtro), `rentals: [rental]`, `count: 1` e `seq: next_seq` (`$setOnInsert` só se aplica quando o documento é criado).

O `find_one` antes só serve para saber que número teria um balde novo. Não decide nada: a decisão "há balde aberto ou não" é tomada pelo filtro do `updateOne`, no servidor.

### Porque é seguro com duas chamadas ao mesmo tempo para o mesmo cliente

**Um balde nunca passa de 50.** Cada `updateOne` num documento é atómico: o MongoDB avalia o filtro e aplica `$push` e `$inc` no mesmo documento sem que outra escrita se meta pelo meio. Se duas chamadas encontram o mesmo balde com `count: 49`, a primeira a escrever deixa-o com 50. A segunda tem um conflito de escrita nesse documento; o MongoDB repete-a internamente, volta a avaliar o filtro, e `count < 50` já é falso. Nada coincide, por isso o upsert cria um balde novo. Os alugueres nunca se perdem nem vão para um balde cheio.

**O que não é garantido sem índices: dois baldes abertos.** Quando o cliente não tem balde aberto, duas chamadas simultâneas podem ambas não encontrar nada e ambas inserir. Ficavam dois baldes abertos (e, como as duas leram o mesmo `last`, com o mesmo `seq`). Os dois iam enchendo em paralelo, o que estraga a ordem e a regra de 50 por balde fechado. É o mesmo problema de qualquer "procura e, se não existir, cria": entre a procura e a criação não há nenhum bloqueio, e o upsert não é atómico entre documentos diferentes.

**O que é preciso: os dois índices únicos.** Com `one_open_bucket` (único parcial em `customer_id` para `count < 50`) e `customer_seq` (único em `customer_id, seq`), o segundo insert falha com `DuplicateKeyError`. `add_rental` apanha o erro e repete a chamada: agora o filtro encontra o balde aberto que a outra chamada criou e acrescenta-lhe o aluguer. O índice parcial é o essencial, porque é ele que diz "um aberto por cliente". O `customer_seq` cobre o caso de dois baldes com o mesmo número. O MongoDB só repete sozinho um upsert depois de um `DuplicateKeyError` quando o filtro é uma igualdade nos campos do índice; aqui o filtro tem `$lt`, por isso a repetição está no código.

### O teste

8 threads acrescentam 15 alugueres cada uma ao cliente 999999 (120 no total), numa coleção à parte. Antes de cada aluguer as 8 esperam umas pelas outras numa `Barrier`, para chamarem `add_rental` ao mesmo tempo, também quando um balde acaba de encher.

```
$ uv run python buckets.py concurrency
bucket seq 1: count 50, rentals in the array 50
bucket seq 2: count 50, rentals in the array 50
bucket seq 3: count 20, rentals in the array 20
rentals stored: 120, distinct: 120, missing: []
add_rental calls repeated after a DuplicateKeyError: 0
```

O resultado é sempre 50, 50 e 20, sem alugueres perdidos nem repetidos. A janela do problema (duas chamadas a inserir o mesmo balde novo) é muito curta. Nas corridas que fiz nunca aconteceu, nem sem os índices únicos (`concurrency --no-unique`, mesmo resultado): as threads em Python, com uma ida ao servidor para o `find_one`, não chegam ao `updateOne` exatamente ao mesmo tempo. Isso não torna o código seguro sem os índices. Torna o erro raro, o que é pior: com muitos pedidos em produção acontece, e ninguém consegue reproduzi-lo. Os índices fazem com que a base de dados o impeça sempre, aconteça a corrida ou não.

## Tarefas 3 e 4: carregamento

`load` cria a coleção e os índices, percorre `rentals` por `rental_date` (e `_id` em caso de empate) e chama `add_rental` para cada aluguer. `rental_history` é feita com uma agregação (`$sort`, `$group` com `$push`, `$out`).

```
$ uv run python buckets.py load
rental_buckets: 51805 rentals added with add_rental in 37.7s, 1605 buckets
rental_history: 997 documents in 0.3s
buckets: 1605, rentals in buckets: 51805, largest bucket: 50, full buckets: 612
customer 380, bucket seq 1: 50 rentals
customer 380, bucket seq 2: 47 rentals
```

- Os 51.805 alugueres estão nos baldes, e **nenhum balde tem mais de 50**.
- **O cliente 380 tem 2 baldes, com 50 e 47 alugueres.**
- `rental_history` tem 997 documentos: os clientes 647 e 978 não têm alugueres.

## Tarefa 5: cliente 380

```
$ uv run python buckets.py compare
customer 380: 97 rentals
  rental_buckets seq 1: 50 rentals, 6,494 bytes
  rental_buckets seq 2: 47 rentals, 6,136 bytes
  rental_buckets total: 12,630 bytes
  rental_history: 1 document, 12,533 bytes
  the 20 most recent rentals are the same in both (newest: 86888)
median time to read the 20 most recent rentals (2,000 reads each):
  rental_buckets (last 1 or 2 buckets):       0.536 ms
  rental_history with $slice: -20:            0.362 ms
  rental_history, whole document:             0.486 ms
largest rental_history document: 12,533 bytes (97 rentals)
largest rental_buckets document: 6,576 bytes (50 rentals)
```

| | `rental_buckets` | `rental_history` |
|---|------------------|------------------|
| Documentos do cliente 380 | 2 (50 + 47) | 1 (97) |
| Tamanho (`bsonsize`) | 6.494 + 6.136 = 12.630 bytes | 12.533 bytes |
| Ler os 20 mais recentes (mediana) | 0,536 ms | 0,362 ms com `$slice: -20` (0,486 ms o documento todo) |

Para o cliente com mais alugueres do Pagila, **os baldes não ganham**: 97 alugueres cabem em 12 KB, o histórico embutido lê-se num documento e o `$slice` só envia 20 elementos. Os baldes até custam um pouco mais (um `sort` por `seq` e um documento de 6 KB com 47 alugueres para usar 20). Os tamanhos totais são quase iguais: o que os baldes acrescentam (`customer_id`, `seq`, `count`, `_id` por balde) é pouco.

### Quando é que o bucket pattern compensa

Para ver o efeito do crescimento, `large` repete a comparação com um cliente inventado com 20.000 alugueres (e apaga-o no fim):

```
$ uv run python buckets.py large
made-up customer 0: 20,000 rentals
  rental_history: 1 document, 2,668,929 bytes
  rental_buckets: 400 documents, the newest 6,613 bytes
median time to read the 20 most recent rentals (200 reads each):
  rental_buckets (last 1 or 2 buckets):       0.530 ms
  rental_history with $slice: -20:            4.525 ms
  rental_history, whole document:             52.806 ms
mean time of one $push of a new rental (200 pushes each):
  into the bucket:                            0.425 ms
  into the rental_history document:           9.244 ms
```

Os baldes ficam com o mesmo custo (0,53 ms, tal como com 97 alugueres), porque leem sempre 1 ou 2 documentos de no máximo 50 itens. O histórico embutido piora com o tamanho: o `$slice` só reduz o que é **enviado**, mas o servidor tem de carregar e percorrer o documento de 2,6 MB (8 vezes mais lento); ler o documento inteiro é 100 vezes mais lento; e cada `$push` reescreve um documento de 2,6 MB (20 vezes mais lento). Com cerca de 125.000 alugueres o documento chegaria aos 16 MB e deixava de aceitar escritas.

O bucket pattern compensa quando:
- **a lista cresce sem limite** (histórico, logs, leituras de sensores, mensagens), e não se sabe quanto pode crescer;
- **a leitura habitual é "os mais recentes" ou um intervalo**, não a lista inteira: lê-se só o balde certo;
- **há muitas escritas pequenas** (um aluguer de cada vez): o `$push` vai para um documento pequeno;
- comparado com um documento por item (a coleção `rentals`), junta N itens num documento e num conjunto de entradas de índice, por isso há menos documentos e índices mais pequenos.

Não compensa quando a lista é pequena e limitada (como os 97 alugueres do cliente 380, ou os atores de um filme): um documento só é mais simples e tão ou mais rápido. Aí embute-se, como no exercício.
