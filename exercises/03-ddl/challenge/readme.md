# Desafio: a base de dados rejeita ISBNs inválidos

## Enunciado

**Challenge (mandatory).**

**Goal.** Make the database itself reject invalid ISBNs.

**Starting point.** An empty database (`./scripts/create-db.sh ch03`). You may add the domain to your library schema; if you do not, use this table:

```sql
CREATE TABLE book (
    book_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    isbn    isbn13 NOT NULL UNIQUE,
    title   text NOT NULL
);
```

An ISBN-13 has 13 digits. Hyphens may appear between digits, never at the start or the end and never two in a row. The last digit is a check digit: multiply the first 12 digits alternately by 1 and 3, add the results, and the check digit is `(10 - sum % 10) % 10`.

**Tasks.**

1. Write an IMMUTABLE SQL function `is_valid_isbn13(text) RETURNS boolean` that checks the format and the check digit.
2. Create `DOMAIN isbn13 AS text CHECK (is_valid_isbn13(VALUE))` and use it in the `book` table.
3. Prove that these values are accepted: `978-0-306-40615-7`, `9781402894626`, `978-3-16-148410-0`. Prove that these are rejected: `978-0-306-40615-8` (wrong check digit), `978-0-306-4061` (too short), `-9780306406157` (leading hyphen), `978--0306406157` (two hyphens in a row).
4. Explain why the function must be IMMUTABLE.

**Deliverables.** `isbn.sql` with the function, the domain, the table and the 7 test inserts. `README.md` with the output of `isbn.sql` and the explanation of task 4.

**Done when.** The 3 valid values are inserted, the 4 invalid ones fail with a domain check error, and the explanation is correct.

---

## Como correr

```bash
./scripts/create-db.sh ch03 --reset
docker compose exec -T postgres psql -U postgres -d ch03 < exercises/03-ddl/challenge/isbn.sql
```

## Como a função funciona

1. **Formato:** a expressão regular `^[0-9]+(-[0-9]+)*$` aceita dígitos com hífenes só *entre* dígitos. Por isso o hífen no início, no fim ou repetido falha logo.
2. **Tamanho:** sem os hífenes, tem de haver exatamente 13 dígitos.
3. **Dígito de controlo:** multiplicam-se os primeiros 12 dígitos alternadamente por 1 e 3, somam-se, e o dígito de controlo tem de ser `(10 - soma % 10) % 10`.

Os três passos estão num `CASE` e não em `AND`, porque o SQL não garante a ordem de avaliação de um `AND`. Com `CASE`, a soma só é calculada depois de se saber que o texto são mesmo dígitos, e nunca há um erro de conversão para `integer`.

Exemplo, `978-0-306-40615-7`: os 12 primeiros dígitos dão 9 + 21 + 8 + 0 + 3 + 0 + 6 + 12 + 0 + 18 + 1 + 15 = 93, e `(10 - 93 % 10) % 10 = 7`, que é o último dígito.

## Output de `isbn.sql`

```
CREATE FUNCTION
CREATE DOMAIN
CREATE TABLE
INSERT 0 1
INSERT 0 1
INSERT 0 1
ERROR:  value for domain isbn13 violates check constraint "isbn13_valid"
ERROR:  value for domain isbn13 violates check constraint "isbn13_valid"
ERROR:  value for domain isbn13 violates check constraint "isbn13_valid"
ERROR:  value for domain isbn13 violates check constraint "isbn13_valid"
 book_id |       isbn        |  title  
---------+-------------------+---------
       1 | 978-0-306-40615-7 | Valid 1
       2 | 9781402894626     | Valid 2
       3 | 978-3-16-148410-0 | Valid 3
(3 rows)
```

| Valor | Resultado | Motivo |
|---|---|---|
| `978-0-306-40615-7` | aceite | válido |
| `9781402894626` | aceite | válido |
| `978-3-16-148410-0` | aceite | válido |
| `978-0-306-40615-8` | rejeitado | dígito de controlo errado (devia ser 7) |
| `978-0-306-4061` | rejeitado | só 11 dígitos |
| `-9780306406157` | rejeitado | hífen no início |
| `978--0306406157` | rejeitado | dois hífenes seguidos |

Os 3 válidos entram e os 4 inválidos falham com `value for domain isbn13 violates check constraint "isbn13_valid"`. O `SELECT` final mostra que só ficaram os 3 válidos.

## Porque é que a função tem de ser IMMUTABLE

`IMMUTABLE` é uma promessa à base de dados: para os mesmos argumentos, a função devolve **sempre** o mesmo resultado. Não lê tabelas, não usa `now()` nem configurações da sessão. A minha função cumpre isto, porque só faz operações sobre o texto que recebe.

É preciso porque uma constraint é uma regra sobre os dados guardados, e o veredicto não pode depender de quando ou onde é calculado:

- **Os dados guardados têm de continuar válidos.** A constraint é avaliada em cada `INSERT` e `UPDATE`, mas também ao validar dados já existentes (por exemplo num `ALTER DOMAIN`) e ao restaurar uma cópia de segurança. Se a função pudesse dar respostas diferentes para o mesmo ISBN, um valor aceite hoje podia ser recusado amanhã, e a base de dados ficava com dados que já não cumprem a própria regra.
- **A base de dados só pode confiar nela se for IMMUTABLE.** O PostgreSQL exige funções `IMMUTABLE` em índices sobre expressões e em colunas geradas (uma função `VOLATILE` ali dá `functions in index expression must be marked IMMUTABLE`), e o planeador pode calcular o resultado uma vez e reutilizá-lo, em vez de o recalcular para cada linha.

Uma nota de rigor: o PostgreSQL não verifica sozinho que a função é mesmo imutável, e aceita um `CHECK` com uma função `VOLATILE`. A responsabilidade é de quem escreve: só se marca `IMMUTABLE` uma função que de facto o é. Marcá-la `IMMUTABLE` e depois fazê-la ler uma tabela seria mentir à base de dados, e a constraint deixava de ser fiável.
