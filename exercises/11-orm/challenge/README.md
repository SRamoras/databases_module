# Desafio 11: um teste que falha com N+1

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `models.py` | Os modelos do exercício 11 (as mesmas 6 tabelas) |
| `films.py` | O código testado: `list_films(session, limit)` devolve os primeiros filmes com atores e categorias, com `selectinload` |
| `tests/conftest.py` | Tarefas 1 e 2: fixtures `engine`, `session`, `statements` (conta as instruções com `before_cursor_execute`) e `assert_max_queries(n)` |
| `tests/test_queries.py` | Tarefa 3: os 100 primeiros filmes com atores e categorias dentro de `assert_max_queries(3)` |
| `pyproject.toml` | Projeto uv (dependências: `sqlalchemy>=2`, `psycopg[binary]`, `pytest`) |

## Como correr

A partir da raiz do repositório:

```bash
./scripts/create-db.sh ex11 --pagila     # a base de dados do exercício 11

cd exercises/11-orm/challenge
uv sync
export DATABASE_URL="postgresql://postgres:<POSTGRES_PASSWORD do .env>@localhost:5432/ex11"
uv run pytest -v
```

## Como funciona

- `statements` regista um listener `before_cursor_execute` no engine no início do teste e remove-o no fim. Cada instrução SQL enviada ao PostgreSQL fica numa lista.
- `assert_max_queries(n)` é um context manager (`@contextmanager`): guarda o tamanho da lista à entrada do `with` e, à saída, falha o teste com `pytest.fail` se correram mais de `n` instruções. A mensagem diz quantas correram e mostra as 5 primeiras, para se perceber logo qual é a query repetida.
- O fixture `engine` abre uma ligação antes dos testes. Na primeira ligação o dialeto corre queries próprias (versão do servidor, schema atual), e assim nunca entram na contagem.
- O teste usa 3 como limite: 1 query para os filmes, 1 para os atores de todos (`selectinload(Film.actors)`) e 1 para as categorias de todos (`selectinload(Film.categories)`).

## Com eager loading: passa

```
$ uv run pytest -v
============================= test session starts ==============================
platform linux -- Python 3.13.11, pytest-9.2.0, pluggy-1.7.0
collecting ... collected 2 items

tests/test_queries.py::test_list_films_has_no_n_plus_one PASSED          [ 50%]
tests/test_queries.py::test_assert_max_queries_counts_statements PASSED  [100%]

============================== 2 passed in 0.27s ===============================
```

## Sem eager loading: falha

Comentei a linha `.options(selectinload(Film.actors), selectinload(Film.categories))` em `films.py` e corri outra vez:

```
$ uv run pytest -v
============================= test session starts ==============================
platform linux -- Python 3.13.11, pytest-9.2.0, pluggy-1.7.0
collecting ... collected 2 items

tests/test_queries.py::test_list_films_has_no_n_plus_one FAILED          [ 50%]
tests/test_queries.py::test_assert_max_queries_counts_statements PASSED  [100%]

=================================== FAILURES ===================================
______________________ test_list_films_has_no_n_plus_one _______________________
expected at most 3 SQL statements, but 201 ran. First ones:
  1. SELECT film.film_id, film.title, film.description, film.release_year, film.language_id, film.origina
  2. SELECT actor.actor_id, actor.first_name, actor.last_name, actor.last_update 
  3. SELECT category.category_id, category.name, category.last_update 
  4. SELECT actor.actor_id, actor.first_name, actor.last_name, actor.last_update 
  5. SELECT category.category_id, category.name, category.last_update 
=========================== short test summary info ============================
FAILED tests/test_queries.py::test_list_films_has_no_n_plus_one - Failed: exp...
========================= 1 failed, 1 passed in 0.27s ==========================
```

201 = 1 query para os filmes + 100 para os atores + 100 para as categorias (duas cargas lazy por filme). As instruções 2 a 5 mostram o padrão: atores, categorias, atores, categorias... Depois voltei a pôr a linha.
