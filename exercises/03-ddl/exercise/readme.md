# Exercício: biblioteca municipal em PostgreSQL

## Enunciado

**Goal.** Implement the municipal library in PostgreSQL with data types and constraints that enforce its rules.

**Tasks.**

1. Write `schema.sql`, which creates every table of the library. Use identity columns for surrogate keys, numeric for money and timestamptz or date for dates. Include at least: one CHECK (for example the condition of a copy, or a due date after the loan date); one composite UNIQUE; one ON DELETE RESTRICT and one ON DELETE CASCADE, each justified in a comment.
2. Write `invalid.sql` with 5 INSERT or DELETE statements that must fail, each rejected by a different constraint. Above each statement, add a comment with the name of the constraint that rejects it.

**Deliverables.** `schema.sql`, `invalid.sql`, and this `README.md` with the output of running `invalid.sql`.

**Done when.** `schema.sql` runs on an empty database without errors, and each of the 5 statements in `invalid.sql` fails with the error of the constraint named in its comment.

---

## Como correr

```
./scripts/create-db.sh ex03
docker compose exec -T postgres psql -U postgres -d ex03 -v ON_ERROR_STOP=1 < exercises/03-ddl/exercise/schema.sql
docker compose exec -T postgres psql -U postgres -d ex03 < exercises/03-ddl/exercise/invalid.sql
```

O `schema.sql` corre numa base de dados vazia sem erros (11 `CREATE`, nenhum `ERROR`).

## O que o schema usa

| Pedido | Onde está |
|---|---|
| Chaves substitutas com identity | todas as tabelas: `integer GENERATED ALWAYS AS IDENTITY` |
| `numeric` para dinheiro | `fine.amount numeric(10,2)` |
| `date` / `timestamptz` | `date` em `acquired_at`, `loan_date`, `due_date`, `return_date`, `paid_at`, `registered_at`; `timestamptz` em `reservation.reserved_at` |
| CHECK | `copy_condition_valid`, `loan_due_date_14_days`, `loan_return_after_loan`, `reservation_status_valid`, `fine_amount_positive`, `isbn_13_digits`, e mais |
| UNIQUE composto | `book_author_position_unique (book_id, author_order)` |
| ON DELETE RESTRICT | `book.publisher_id`, `book_copy.book_id`, `loan.reader_id`, `loan.copy_id`, `reservation.*`, `fine.loan_id`, `book_author.author_id` |
| ON DELETE CASCADE | `book_author.book_id` |

Cada `RESTRICT` e o `CASCADE` têm um comentário a justificar no `schema.sql`. Resumindo: apaga-se em cascata só o que não tem sentido sem o pai (os autores de um livro), e recusa-se apagar tudo o que deixaria perder histórico (livros de uma editora, empréstimos de um leitor, multas).

Também tem dois índices únicos parciais que implementam regras do enunciado: `one_open_loan_per_copy` (uma cópia só está num empréstimo aberto) e `one_active_reservation_per_reader_book`.

Não estão no schema as regras que precisam de trigger ou da aplicação (máximo de 5 empréstimos abertos por leitor, ordem das reservas, multa de 0,50 por dia de atraso).

## Output de `invalid.sql`

Os dados de preparação (um editor, dois autores, um livro, duas cópias, um leitor e um empréstimo) são válidos e entram sem erro. Depois cada um dos 5 comandos falha com a constraint do comentário:

```
1) copy_condition_valid (CHECK)
ERROR:  new row for relation "book_copy" violates check constraint "copy_condition_valid"
DETAIL:  Failing row contains (3, 1, BC-0003, 2026-10-28, broken).

2) loan_due_date_14_days (CHECK)
ERROR:  new row for relation "loan" violates check constraint "loan_due_date_14_days"
DETAIL:  Failing row contains (2, 1, 2, 2026-10-02, 2026-10-20, null).

3) book_author_position_unique (composite UNIQUE)
ERROR:  duplicate key value violates unique constraint "book_author_position_unique"
DETAIL:  Key (book_id, author_order)=(1, 1) already exists.

4) book_publisher_id_fkey (FOREIGN KEY, ON DELETE RESTRICT)
ERROR:  update or delete on table "publisher" violates foreign key constraint "book_publisher_id_fkey" on table "book"
DETAIL:  Key (publisher_id)=(1) is still referenced from table "book".

5) one_open_loan_per_copy (partial UNIQUE index)
ERROR:  duplicate key value violates unique constraint "one_open_loan_per_copy"
DETAIL:  Key (copy_id)=(1) already exists.
```

| # | Constraint | Tipo | Porque falha |
|---|---|---|---|
| 1 | `copy_condition_valid` | CHECK | `'broken'` não é new, good, worn nem damaged |
| 2 | `loan_due_date_14_days` | CHECK | o prazo não é 14 dias depois do empréstimo |
| 3 | `book_author_position_unique` | UNIQUE composto | dois autores na posição 1 do mesmo livro |
| 4 | `book_publisher_id_fkey` | FOREIGN KEY, RESTRICT | a editora ainda tem um livro |
| 5 | `one_open_loan_per_copy` | UNIQUE parcial | a cópia já está num empréstimo aberto |

## Nota sobre como o output foi gerado

O output acima foi produzido com `psql` contra um PostgreSQL 16.15 local (`createdb ex03` e os mesmos dois comandos `psql`, sem o `docker compose exec`), porque o Docker não estava disponível onde corri os ficheiros. Os ficheiros são os mesmos; se correres com o `docker compose`, o texto dos erros é igual, só podem mudar os números dentro do `DETAIL`, se a base de dados não estiver vazia.