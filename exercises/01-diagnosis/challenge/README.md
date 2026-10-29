# Desafio 01: Escritas concorrentes, ficheiro JSON vs PostgreSQL

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `json_race.py` | 10 processos acrescentam 1000 registos cada a `records.json` (ler tudo, acrescentar um, escrever tudo), sem lock |
| `pg_race.py` | 10 processos, cada um com a sua ligação, inserem 1000 registos cada na tabela `record` com um `INSERT` por registo |
| `pyproject.toml`, `uv.lock` | Projeto uv (dependência: `psycopg[binary]`) |

`records.json` é gerado ao correr o script e não é submetido (está no `.gitignore`).

## Como correr

A partir da raiz do repositório, com os motores a correr (`docker compose up -d`).

Criar a base de dados e a tabela:

```bash
./scripts/create-db.sh ch01
docker compose exec -T postgres psql -U postgres -d ch01 -v ON_ERROR_STOP=1 \
  -c "CREATE TABLE IF NOT EXISTS record (worker integer NOT NULL, n integer NOT NULL);"
```

Instalar as dependências e correr os scripts:

```bash
cd exercises/01-diagnosis/challenge
uv sync

uv run json_race.py              # escrita com ficheiro temporário + os.replace
uv run json_race.py --in-place   # escrita diretamente por cima do ficheiro

DATABASE_URL="postgresql://postgres:<POSTGRES_PASSWORD do .env>@localhost:5432/ch01" uv run pg_race.py
```

Cada script começa do zero: `json_race.py` escreve `[]` em `records.json` e `pg_race.py` faz `TRUNCATE record` (e cria a tabela se não existir). Por isso basta voltar a correr o script para repetir a experiência.

## Resultados (3 execuções de cada)

Esperado: 10 processos × 1000 registos = **10 000**.

`uv run json_race.py`:

```
== json_race run 1
records in file: 1059 (expected 10000), file is valid JSON
failed writes:   0
== json_race run 2
records in file: 1060 (expected 10000), file is valid JSON
failed writes:   0
== json_race run 3
records in file: 1054 (expected 10000), file is valid JSON
failed writes:   0
```

`uv run json_race.py --in-place`:

```
== json_race --in-place run 1
records in file: 0 (expected 10000), file is CORRUPTED, not valid JSON
failed writes:   9973
== json_race --in-place run 2
records in file: 0 (expected 10000), file is CORRUPTED, not valid JSON
failed writes:   9986
== json_race --in-place run 3
records in file: 0 (expected 10000), file is CORRUPTED, not valid JSON
failed writes:   9694
```

`uv run pg_race.py`:

```
== pg_race run 1
SELECT count(*) FROM record: 10000 (expected 10000)
== pg_race run 2
SELECT count(*) FROM record: 10000 (expected 10000)
== pg_race run 3
SELECT count(*) FROM record: 10000 (expected 10000)
```

| Execução | JSON (`os.replace`) | JSON (`--in-place`) | PostgreSQL |
|----------|---------------------|---------------------|------------|
| 1 | 1059 | 0 (ficheiro corrompido) | 10 000 |
| 2 | 1060 | 0 (ficheiro corrompido) | 10 000 |
| 3 | 1054 | 0 (ficheiro corrompido) | 10 000 |

## Porque é que os números são diferentes

**JSON: perda de atualizações (*lost update*).** Cada escrita é um *read-modify-write* em três passos separados: ler o ficheiro, acrescentar em memória, escrever o ficheiro todo. Nada impede que dois processos leiam a mesma versão ao mesmo tempo. Se os 10 processos leem um ficheiro com 500 registos, cada um escreve a sua versão com 501, e só a última escrita sobrevive: 9 registos perdem-se sem nenhum erro. Por isso fica só cerca de 10% dos registos, e o número muda de execução para execução, porque depende de como o sistema operativo intercala os processos.

**JSON escrito no próprio ficheiro: corrupção.** `open("w")` esvazia o ficheiro antes de escrever. Um processo que leia nesse instante encontra um ficheiro vazio ou incompleto (escrita falhada). Pior: se dois processos abrem o ficheiro ao mesmo tempo e escrevem conteúdos de tamanhos diferentes, o mais curto fica com o fim do mais comprido colado a seguir. O ficheiro deixa de ser JSON válido, todas as leituras seguintes falham e perdem-se **todos** os registos. É o mesmo que acontece quando um processo falha a meio de uma escrita.

**PostgreSQL: 10 000 em todas as execuções.** Cada `INSERT` só acrescenta uma linha nova: o motor não lê a tabela, não a altera em memória e não a reescreve, por isso não há uma versão antiga que um processo possa escrever por cima do trabalho de outro. O motor controla o acesso concorrente às páginas da tabela (locks internos e MVCC), e cada `INSERT` é uma transação atómica e durável: ou fica gravado por inteiro ou não fica, e depois do commit fica registado no WAL, mesmo que o servidor falhe. As 10 ligações escrevem em simultâneo sem se pisarem.
