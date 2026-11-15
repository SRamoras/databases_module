# Desafio 14: receita diária incremental com `$merge`

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `daily_revenue.py` | O relatório: `run_report(db)` (uma execução incremental) e `full_recompute(db)` (o mesmo relatório calculado do zero, para comparar) |
| `tests/test_daily_revenue.py` | Tarefa 3: o teste |
| `pyproject.toml` | Projeto uv (dependências: `pymongo`, `pytest`) |

## Como correr

Precisa da coleção `rentals` do exercício 13 em `pagila_docs`.

```bash
cd exercises/14-pipelines/challenge
uv sync
export MONGO_URL="mongodb://root:<MONGO_ROOT_PASSWORD do .env>@localhost:27017/?authSource=admin"

uv run python daily_revenue.py      # uma execução sobre pagila_docs
uv run pytest -v -s                 # o teste (numa cópia, em ch14_test)
```

## Como funciona

`daily_revenue` tem um documento por dia (UTC):

```js
{ _id: ISODate('2026-07-28T00:00:00.000Z'), rentals: 20, revenue: Decimal128('52.81') }
```

`report_state` guarda o watermark:

```js
{ _id: 'daily_revenue', watermark: 87559 }    // o maior rentals._id já processado
```

Cada execução de `run_report`:

1. Lê o watermark (na primeira não há nenhum).
2. Encontra o maior `_id` acima do watermark (`upto`). Se não houver nenhum, não faz nada.
3. Encontra os **dias** dos alugueres com `_id` entre o watermark e `upto` (`$dateTrunc` ao dia).
4. **Recalcula esses dias a partir de todos os seus alugueres**, antigos e novos: `$match` com um intervalo `[dia, dia + 1)` por dia (um `$or` de intervalos em `rental_date`, que pode usar um índice), `$group` por dia e `$merge` com `on: "_id"`, `whenMatched: "replace"`, `whenNotMatched: "insert"`. Cada dia recalculado substitui o documento inteiro; um dia novo é inserido; os outros dias não são tocados.
5. **Só depois** move o watermark para `upto`.

Na primeira execução não há watermark, por isso calcula todos os dias.

A ordem dos passos 4 e 5 é o que torna o relatório seguro se o processo parar a meio. Se parar depois do `$merge` e antes de mover o watermark, a execução seguinte encontra os mesmos alugueres acima do watermark, recalcula os mesmos dias e obtém os mesmos valores. Se fosse ao contrário (watermark primeiro), uma falha a meio deixava alugueres para trás, que nenhuma execução voltaria a ver.

```
$ uv run python daily_revenue.py
days recomputed: 1476, watermark: 87559, days in daily_revenue: 1476
$ uv run python daily_revenue.py
days recomputed: 0, watermark: 87559, days in daily_revenue: 1476
```

## Tarefa 3: o teste

O teste copia `pagila_docs.rentals` para a base de dados `ch14_test` (`$out` com `db` e `coll`) e corre tudo lá. Assim as coleções dos exercícios nunca mudam, e a base de dados de teste é apagada no fim.

1. Corre o relatório sobre a coleção inteira e verifica que é igual a um cálculo do zero.
2. Insere 5 alugueres com `_id` acima do máximo atual: 3 em 2026-07-28 (1.99, 2.99 e 0.99, um dia que já tem alugueres) e 2 em 2026-07-29 (4.99 e 3.99, um dia novo).
3. Corre o relatório outra vez e verifica que os dias recalculados **e** os documentos que mudaram são exatamente 2026-07-28 e 2026-07-29, com os valores certos (+3 alugueres e +5.97 no dia 28; 2 alugueres e 8.98 no dia 29), e que há um dia a mais.
4. Compara `daily_revenue` inteira com um cálculo do zero (`full_recompute`).
5. Corre o relatório uma terceira vez e verifica que não recalcula nenhum dia e que `daily_revenue` fica igual.

```
$ uv run pytest -v -s
============================= test session starts ==============================
platform linux -- Python 3.13.11, pytest-9.2.0, pluggy-1.7.0
collecting ... collected 1 item

tests/test_daily_revenue.py::test_incremental_report
run 1: 1476 days computed, 1476 days in daily_revenue, watermark 87559
  2026-07-28: rentals 20, revenue 52.81
  2026-07-29: (none)
inserted 5 rentals: _id 87560 to 87564
run 2: days recomputed ['2026-07-28', '2026-07-29'], days whose document changed ['2026-07-28', '2026-07-29']
  2026-07-28: rentals 23, revenue 58.78
  2026-07-29: rentals 2, revenue 8.98
run 2 equals a full recomputation: 1477 days
run 3: days recomputed 0, daily_revenue unchanged: True
PASSED

============================== 1 passed in 1.18s ===============================
```

- **A segunda execução só toca em 2 dias:** recalcula 2026-07-28 (20 → 23 alugueres, 52.81 → 58.78) e cria 2026-07-29 (2 alugueres, 8.98). Os outros 1.475 dias ficam iguais.
- **O resultado é igual a um cálculo do zero** (1.477 dias).
- **A terceira execução não muda nada:** não há alugueres acima do watermark.

## Porque é que recalcular o dia inteiro é mais seguro do que somar os valores novos

A alternativa seria, para cada aluguer novo, fazer `$inc` de `rentals: 1` e `revenue: amount` no dia dele. Isso tem vários problemas que o recálculo não tem:

- **Repetir uma execução conta duas vezes.** Se o processo falhar depois dos `$inc` e antes de mover o watermark, a execução seguinte volta a somar os mesmos alugueres. Com `$inc` o resultado depende de quantas vezes o passo correu; com `replace` de um valor calculado a partir da fonte, correr uma, duas ou dez vezes dá o mesmo (é idempotente). Foi o que a terceira execução do teste mostrou.
- **Um erro nunca se corrige sozinho.** Com `$inc`, um valor errado num dia (uma falha a meio, um bug numa versão antiga do script, um aluguer apagado ou corrigido na fonte) fica errado para sempre, e cada soma seguinte parte desse erro. Recalcular o dia a partir de todos os seus alugueres repõe o valor certo sempre que esse dia volta a ser tocado.
- **Alterações a alugueres antigos.** Se o `amount` de um aluguer já processado mudar (um pagamento que chegou depois), somar não sabe a diferença entre o valor antigo e o novo. O recálculo usa o valor atual. (Para o relatório saber dessas alterações seria preciso também um campo de "última alteração" no watermark, porque o `_id` não muda. Ver a limitação abaixo.)
- **O custo é pequeno.** Recalcular um dia lê os alugueres desse dia (umas dezenas), não a coleção inteira. A execução incremental continua barata.

Limitação: o watermark é o `_id`, por isso o relatório só vê alugueres **novos**. Um aluguer antigo alterado (por exemplo, `amount` corrigido) só é refletido quando o seu dia voltar a ser recalculado por causa de outro aluguer novo, ou num cálculo do zero. Também supõe que os `_id` crescem pela ordem de inserção, como os `rental_id` do PostgreSQL. Um aluguer inserido com um `_id` abaixo do watermark nunca seria visto.
