# Deadlock (tarefa 3)

Base de dados `ex08`, depois de `setup.sql`. Clientes 1 e 2 com `balance = 100`. Duas sessões `psql`, com os comandos executados pela ordem da tabela. Os resultados são o output real das duas sessões.

| Passo | Sessão A | Sessão B |
|-------|----------|----------|
| 1 | `BEGIN;` | |
| 2 | `UPDATE customer SET balance = balance - 10 WHERE customer_id = 1;` → `UPDATE 1` (A bloqueia a linha do cliente 1) | |
| 3 | | `BEGIN;` |
| 4 | | `UPDATE customer SET balance = balance - 10 WHERE customer_id = 2;` → `UPDATE 1` (B bloqueia a linha do cliente 2) |
| 5 | `UPDATE customer SET balance = balance - 10 WHERE customer_id = 2;` → **fica à espera de B** | |
| 6 | | `UPDATE customer SET balance = balance - 10 WHERE customer_id = 1;` → **fica à espera de A** |
| | ~1 segundo depois, o `UPDATE` de A falha com `ERROR: deadlock detected` (abaixo) | O `UPDATE` do passo 6 continua → `UPDATE 1` |
| 7 | `ROLLBACK;` | |
| 8 | | `COMMIT;` |
| 9 | `SELECT customer_id, balance FROM customer WHERE customer_id IN (1, 2) ORDER BY customer_id;` → **1: 90.00, 2: 90.00** | |

O resultado final só tem as alterações de B (−10 em cada cliente). A transação de A foi toda desfeita, incluindo o `UPDATE` do cliente 1 do passo 2.

## A mensagem de erro (sessão A)

```
ERROR:  deadlock detected
DETAIL:  Process 5068 waits for ShareLock on transaction 31493; blocked by process 5067.
Process 5067 waits for ShareLock on transaction 31492; blocked by process 5068.
HINT:  See server log for query details.
CONTEXT:  while locking tuple (17,27) in relation "customer"
```

E o que o `HINT` manda ver, no log do servidor (`docker compose logs postgres`):

```
ERROR:  deadlock detected
DETAIL:  Process 5068 waits for ShareLock on transaction 31493; blocked by process 5067.
	Process 5067 waits for ShareLock on transaction 31492; blocked by process 5068.
	Process 5068: UPDATE customer SET balance = balance - 10 WHERE customer_id = 2;
	Process 5067: UPDATE customer SET balance = balance - 10 WHERE customer_id = 1;
HINT:  See server log for query details.
CONTEXT:  while locking tuple (17,27) in relation "customer"
STATEMENT:  UPDATE customer SET balance = balance - 10 WHERE customer_id = 2;
```

### Linha a linha

| Linha | Significado |
|-------|-------------|
| `ERROR: deadlock detected` | O PostgreSQL encontrou um ciclo de esperas que nunca se resolveria sozinho, e cancelou uma das transações (a vítima) para o quebrar. A vítima foi a sessão A. |
| `Process 5068 waits for ShareLock on transaction 31493; blocked by process 5067.` | O processo 5068 (servidor da sessão A) está à espera da transação 31493 (a de B), que corre no processo 5067. Para atualizar uma linha alterada por outra transação ainda aberta, uma transação espera que essa termine, pedindo um `ShareLock` sobre o ID dela. É a espera do passo 5: A quer a linha do cliente 2, que B alterou. |
| `Process 5067 waits for ShareLock on transaction 31492; blocked by process 5068.` | E o contrário: B (5067) espera pela transação 31492, a de A. É o passo 6: B quer a linha do cliente 1, que A alterou. As duas linhas juntas fecham o ciclo A → B → A. |
| `HINT: See server log for query details.` | O cliente não recebe as instruções dos outros processos (podiam ter dados de outros utilizadores). O log do servidor mostra-as: o processo 5068 estava em `... customer_id = 2` e o 5067 em `... customer_id = 1`. |
| `CONTEXT: while locking tuple (17,27) in relation "customer"` | A operação que falhou: a tentativa de bloquear a linha física `(17,27)` (página 17, posição 27) da tabela `customer`, que é a linha do cliente 2. |
| `STATEMENT: ...` (só no log) | A instrução da vítima que foi cancelada. |

### Porque é que a vítima foi A

Uma sessão que espera por um bloqueio só verifica se há deadlock depois de esperar `deadlock_timeout` (1 s por omissão). A começou a esperar primeiro (passo 5), por isso foi a primeira a fazer a verificação. Encontrou o ciclo e cancelou-se a si própria. Assim que A largou os seus bloqueios, o `UPDATE` de B continuou.

## Como prevenir

1. **Bloquear sempre pela mesma ordem.** O deadlock acontece porque A bloqueia 1 e depois 2, e B bloqueia 2 e depois 1. Se todas as transações bloquearem as linhas pela mesma ordem (por exemplo por `customer_id` crescente), B esperaria por A logo no cliente 1, sem ter nada bloqueado, e não há ciclo possível. Numa transferência entre duas contas, isto quer dizer atualizar primeiro a conta com o ID mais baixo, seja ela a de origem ou a de destino.
2. **Bloquear tudo de uma vez, no início.** `SELECT ... FROM customer WHERE customer_id IN (1, 2) ORDER BY customer_id FOR UPDATE;` bloqueia as duas linhas logo no início, pela mesma ordem.
3. **Transações curtas.** Quanto menos tempo os bloqueios duram, menor a janela para um ciclo.
4. **Repetir a vítima.** Um deadlock não corrompe dados: a vítima é desfeita por inteiro (SQLSTATE `40P01`). A aplicação deve apanhar este erro e repetir a transação desde o início. Mesmo com as regras acima, isto é uma boa rede de segurança.
