# Lost update e as duas correções (tarefas 1 e 2)

Base de dados `ex08`, depois de `setup.sql` (cada cliente começa com `balance = 100`). Duas sessões `psql` (A e B) na mesma base de dados, com os comandos executados pela ordem das tabelas (de cima para baixo). Antes de cada cenário, o saldo foi reposto:

```sql
UPDATE customer SET balance = 100 WHERE customer_id = 1;
```

Os resultados abaixo são o output real das duas sessões `psql`.

## Tarefa 1: lost update

Cada sessão quer levantar 10: lê o saldo com `SELECT` e escreve o valor lido menos 10.

| Passo | Sessão A | Sessão B |
|-------|----------|----------|
| 1 | `BEGIN;` | |
| 2 | `SELECT balance FROM customer WHERE customer_id = 1;` → **100.00** | |
| 3 | | `BEGIN;` |
| 4 | | `SELECT balance FROM customer WHERE customer_id = 1;` → **100.00** |
| 5 | `UPDATE customer SET balance = 90 WHERE customer_id = 1;` → `UPDATE 1` | |
| 6 | `COMMIT;` | |
| 7 | | `UPDATE customer SET balance = 90 WHERE customer_id = 1;` → `UPDATE 1` |
| 8 | | `COMMIT;` |
| 9 | `SELECT balance FROM customer WHERE customer_id = 1;` → **90.00** | |

**Resultado: 90.** Houve dois levantamentos de 10, por isso devia ser 80. O levantamento de A perdeu-se.

**Porquê.** As duas sessões leram 100 (passos 2 e 4) antes de qualquer uma escrever. Cada uma calculou o novo saldo na aplicação (100 − 10 = 90) a partir de um valor que, no momento da escrita, já estava desatualizado. O `UPDATE` de B (passo 7) escreve o valor fixo 90 por cima do 90 de A, sem saber que A já tinha mudado a linha. Não há nenhum erro: em `READ COMMITTED`, o `UPDATE` de B vê a versão confirmada por A, mas como escreve uma constante e não `balance - 10`, o resultado é o mesmo. É o padrão *read-modify-write* da sessão 01, agora dentro de uma base de dados.

## Tarefa 2, correção 1: `UPDATE` atómico

As sessões não leem primeiro: o cálculo passa para dentro do `UPDATE`.

| Passo | Sessão A | Sessão B |
|-------|----------|----------|
| 1 | `BEGIN;` | |
| 2 | | `BEGIN;` |
| 3 | `UPDATE customer SET balance = balance - 10 WHERE customer_id = 1 AND balance >= 10 RETURNING balance;` → **90.00**, `UPDATE 1` | |
| 4 | | `UPDATE customer SET balance = balance - 10 WHERE customer_id = 1 AND balance >= 10 RETURNING balance;` → **fica à espera** |
| 5 | `COMMIT;` | |
| | | (o `UPDATE` do passo 4 continua) → **80.00**, `UPDATE 1` |
| 6 | | `COMMIT;` |
| 7 | `SELECT balance FROM customer WHERE customer_id = 1;` → **80.00** | |

**Resultado: 80.** ✔

**Porquê.** O `UPDATE` de A bloqueia a linha até ao `COMMIT`. O `UPDATE` de B tenta bloquear a mesma linha e espera (passo 4). Quando A confirma, o PostgreSQL volta a ler a versão nova da linha (90) e reavalia o `WHERE` (`balance >= 10` continua verdadeiro). Só depois aplica `balance - 10` sobre o 90. O cálculo é feito sobre o valor atual e nunca sobre uma cópia antiga. O `AND balance >= 10` garante, na mesma instrução, que o saldo não fica negativo: se não houver saldo, o `UPDATE` afeta 0 linhas.

## Tarefa 2, correção 2: `SELECT ... FOR UPDATE`

Mantém-se o padrão "ler e depois escrever", mas a leitura bloqueia a linha.

| Passo | Sessão A | Sessão B |
|-------|----------|----------|
| 1 | `BEGIN;` | |
| 2 | `SELECT balance FROM customer WHERE customer_id = 1 FOR UPDATE;` → **100.00** | |
| 3 | | `BEGIN;` |
| 4 | | `SELECT balance FROM customer WHERE customer_id = 1 FOR UPDATE;` → **fica à espera** |
| 5 | `UPDATE customer SET balance = 90 WHERE customer_id = 1;` → `UPDATE 1` | |
| 6 | `COMMIT;` | |
| | | (o `SELECT` do passo 4 continua) → **90.00** |
| 7 | | `UPDATE customer SET balance = 80 WHERE customer_id = 1;` → `UPDATE 1` |
| 8 | | `COMMIT;` |
| 9 | `SELECT balance FROM customer WHERE customer_id = 1;` → **80.00** | |

**Resultado: 80.** ✔

**Porquê.** `FOR UPDATE` bloqueia a linha no momento da leitura, como se fosse uma escrita. O `SELECT ... FOR UPDATE` de B não pode ler enquanto A tiver o bloqueio, por isso espera (passo 4). Quando A confirma, B lê o valor **já atualizado** (90 e não 100), e a conta da aplicação (90 − 10 = 80) fica certa. As leituras e escritas das duas sessões ficam em série nesta linha.

## Comparação

| | Valor lido por B | Saldo final |
|---|---|---|
| Sem proteção | 100 (desatualizado) | 90 ✘ |
| `UPDATE` atómico | (não lê) | 80 ✔ |
| `SELECT ... FOR UPDATE` | 90 (espera por A) | 80 ✔ |

O `UPDATE` atómico é a melhor solução quando o novo valor se calcula numa expressão SQL: uma só instrução, sem ida e volta à aplicação, e o bloqueio dura o mínimo possível. O `FOR UPDATE` é necessário quando a aplicação tem de ler o valor e decidir com lógica que não cabe num `UPDATE` (por exemplo chamar outro serviço antes de escrever).
