# Exercício 11: Modelos SQLAlchemy, SQL gerado e N+1

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `models.py` | Tarefa 1: modelos de `film`, `language`, `actor`, `film_actor`, `category` e `film_category` com as relationships |
| `queries.py` | Tarefa 2: Q1, Q2 e Q3 com o ORM; também corre o SQL escrito à mão e diz se as linhas são iguais |
| `n_plus_one.py` | Tarefa 3: os 100 primeiros filmes com os atores, primeiro com N+1 e depois com `selectinload`, e o número de `SELECT` de cada versão |
| `pyproject.toml` | Projeto uv (`sqlalchemy>=2`, `psycopg[binary]`) |

## Como correr

A partir da raiz do repositório, com os motores a correr (`docker compose up -d`):

```bash
./scripts/create-db.sh ex11 --pagila --reset
cd exercises/11-orm/exercise
uv sync

# O SQLAlchemy precisa do driver no esquema do URL
export DATABASE_URL="postgresql+psycopg://postgres:<password>@localhost:5432/ex11"

uv run python queries.py
uv run python n_plus_one.py
```

Os dois scripts usam `create_engine(..., echo=True)`, por isso todo o SQL aparece no terminal.

## Tarefa 1: modelos

- `Film.language` é N:1. A tabela `film` tem duas FKs para `language` (`language_id` e `original_language_id`), por isso a relationship tem de dizer qual usa: `relationship(foreign_keys=[language_id])`. Sem isso o SQLAlchemy dá `AmbiguousForeignKeysError` ao configurar os mappers.
- `Film.actors` / `Actor.films` e `Film.categories` / `Category.films` são N:M através de `secondary="film_actor"` e `secondary="film_category"`, com `back_populates` dos dois lados.
- `FilmActor` e `FilmCategory` também são mapeadas como classes (chave primária composta), porque as consultas Q1 e Q3 fazem `JOIN` diretamente com elas.
- `rating` usa o tipo enumerado já existente `mpaa_rating` (`create_type=False`, para o SQLAlchemy nunca o tentar criar); `special_features` é `text[]` e `fulltext` é `tsvector`.

## Tarefa 2: SQL escrito à mão e SQL gerado

Output de `queries.py` (sem o log):

```text
=== Q1: 16 linhas, iguais ao SQL escrito à mão ===
('Drama', 152)
('Music', 152)
('Travel', 151)
('Children', 150)
('Foreign', 150)

=== Q2: 489 linhas, iguais ao SQL escrito à mão ===
(141, 'CHICAGO NORTH', 185)
(182, 'CONTROL ANTHEM', 185)
(212, 'DARN FORRESTER', 185)
(349, 'GANGS PRIDE', 185)
(426, 'HOME PITY', 185)

=== Q3: 10 linhas, iguais ao SQL escrito à mão ===
(107, 'GINA', 'DEGENERES', 42)
(102, 'WALTER', 'TORN', 41)
(198, 'MARY', 'KEITEL', 40)
(181, 'MATTHEW', 'CARREY', 39)
(23, 'SANDRA', 'KILMER', 37)
```

### Q1: filmes por categoria

| Escrito à mão | Gerado pelo ORM |
|---------------|-----------------|
| `SELECT c.name, count(*) AS films`<br>`FROM category c JOIN film_category fc ON fc.category_id = c.category_id`<br>`GROUP BY c.category_id, c.name`<br>`ORDER BY films DESC, c.name;` | `SELECT category.name, count(*) AS films`<br>`FROM category JOIN film_category ON film_category.category_id = category.category_id`<br>`GROUP BY category.category_id, category.name`<br>`ORDER BY films DESC, category.name` |

### Q2: filmes mais longos do que a média

| Escrito à mão | Gerado pelo ORM |
|---------------|-----------------|
| `SELECT f.film_id, f.title, f.length`<br>`FROM film f`<br>`WHERE f.length > (SELECT avg(length) FROM film)`<br>`ORDER BY f.length DESC, f.film_id;` | `SELECT film.film_id, film.title, film.length`<br>`FROM film`<br>`WHERE film.length > (SELECT avg(film.length) AS avg_1 FROM film)`<br>`ORDER BY film.length DESC, film.film_id` |

### Q3: os 10 atores com mais filmes

| Escrito à mão | Gerado pelo ORM |
|---------------|-----------------|
| `SELECT a.actor_id, a.first_name, a.last_name, count(*) AS films`<br>`FROM actor a JOIN film_actor fa ON fa.actor_id = a.actor_id`<br>`GROUP BY a.actor_id`<br>`ORDER BY films DESC, a.actor_id`<br>`LIMIT 10;` | `SELECT actor.actor_id, actor.first_name, actor.last_name, count(*) AS films`<br>`FROM actor JOIN film_actor ON film_actor.actor_id = actor.actor_id`<br>`GROUP BY actor.actor_id`<br>`ORDER BY films DESC, actor.actor_id`<br>`LIMIT %(param_1)s::INTEGER` com `{'param_1': 10}` |

### Diferenças que notei

- **Aliases.** O ORM não usa aliases de tabela (`c`, `fc`, `f`): escreve sempre o nome completo (`category.name`). Só os criaria com `aliased()`, que é preciso quando a mesma tabela aparece duas vezes.
- **Nomes automáticos.** Na subconsulta da Q2 o ORM dá o nome `avg_1` à coluna. O nome não tem efeito, porque é uma subconsulta escalar.
- **Parâmetros.** O `LIMIT 10` passa a ser um parâmetro (`%(param_1)s::INTEGER`). O ORM nunca escreve valores literais no SQL, o que protege contra injeção e deixa o PostgreSQL reutilizar o plano.
- **Rótulos reutilizados.** Para ordenar pelo `count(*)` usei o mesmo objeto `.label("films")` no `select` e no `order_by`, por isso o ORM escreve `ORDER BY films DESC` tal como à mão, e não repete o `count(*)`.
- **Joins explícitos.** Escrevi os joins com a condição explícita (`.join(FilmCategory, FilmCategory.category_id == Category.category_id)`). Também funcionaria `.join(FilmCategory)`, porque o SQLAlchemy deduz a condição a partir da única FK entre as duas tabelas.
- **Transação.** O log mostra `BEGIN (implicit)` antes do primeiro `SELECT` e `ROLLBACK` no fim: a `Session` abre sempre uma transação e, como não houve `commit()`, desfaz no fecho.
- Fora isto, o SQL é igual e devolve as mesmas linhas pela mesma ordem (o script compara as listas com `==`).

## Tarefa 3: N+1

`n_plus_one.py` carrega os 100 primeiros filmes por `film_id` e imprime cada título com os nomes dos atores através de `film.actors`. Corre duas vezes, cada uma numa `Session` nova (na mesma sessão os atores já estariam no identity map e a segunda versão não faria consultas). Conta os `SELECT` com o evento `before_cursor_execute` do engine, e confirmei a contagem no log.

**Antes (lazy loading):** 1 consulta para os filmes e depois, para cada filme, uma consulta como esta:

```sql
SELECT actor.actor_id, actor.first_name, actor.last_name, actor.last_update
FROM actor, film_actor
WHERE %(param_1)s::INTEGER = film_actor.film_id AND actor.actor_id = film_actor.actor_id
-- {'param_1': 1}, depois 2, 3, ... 100
```

**Depois (`select(Film).options(selectinload(Film.actors))`):** a mesma consulta para os filmes e uma única consulta para os atores dos 100 filmes:

```sql
SELECT film_actor.film_id, actor.actor_id, actor.first_name, actor.last_name, actor.last_update
FROM film_actor JOIN actor ON actor.actor_id = film_actor.actor_id
WHERE film_actor.film_id IN (%(primary_keys_1)s::INTEGER, ..., %(primary_keys_100)s::INTEGER)
```

Final do output:

```text
N+1 (lazy loading): 101 SELECT
corrigido (selectinload): 2 SELECT
```

| Versão | `SELECT` |
|--------|----------|
| N+1 (lazy loading) | 101 (1 + 100) |
| Corrigido (`selectinload`) | 2 |

Usei `selectinload` e não `joinedload` porque `actors` é uma coleção: com `joinedload` cada filme viria repetido uma vez por ator e o `LIMIT 100` teria de ser posto numa subconsulta.
