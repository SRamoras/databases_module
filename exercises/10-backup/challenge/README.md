# Desafio 10 (opcional): Backups automáticos com retenção e verificação

## Ficheiros

| Ficheiro | Conteúdo |
|----------|----------|
| `backup.sh` | `pg_dump -Fc` de `pagila` mais um ficheiro `.counts` com as linhas de cada tabela, e depois a retenção. Aceita `--now YYYY-MM-DD [HH:MM]`. |
| `verify.sh` | Restaura o último dump (ou o indicado) num contentor `postgres:18` descartável, compara as contagens com o `.counts` e sai com 1 se houver diferenças |
| `schedule.sh` | Agendamento por ciclo (para Windows sem cron): corre `backup.sh` e `verify.sh` a cada `INTERVAL` segundos e escreve num log |

Os backups vão para `backups/pagila/` na raiz do repositório (ou para `$BACKUP_DIR`). `backups/` e `*.dump` estão no `.gitignore`.

## Como correr

A partir da raiz do repositório (Linux, macOS, WSL ou Git Bash no Windows), com os motores a correr e o Pagila carregado:

```bash
exercises/10-backup/challenge/backup.sh
exercises/10-backup/challenge/verify.sh
echo $?   # 0 = backup verificado
```

## Tarefa 1: `backup.sh`

1. `docker compose exec -T postgres pg_dump -Fc pagila > pagila_YYYY-MM-DD_HHMM.dump`
2. Contagem exata (`count(*)`) de cada tabela do schema `public` para `pagila_YYYY-MM-DD_HHMM.counts`, uma linha `tabela|linhas` por tabela (70 tabelas: as 15 do Pagila, as 54 partições de `payment` e a própria `payment`):

   ```
   actor|200
   address|1003
   category|16
   city|600
   country|109
   ...
   ```

   As contagens são feitas por uma consulta que gera um `count(*)` por tabela (`query_to_xml`). Não se usa `reltuples`, que é só uma estimativa.
3. Os dois ficheiros são escritos primeiro como `.tmp` e só depois renomeados. Um backup interrompido nunca fica com o nome de um backup válido.
4. **Retenção:**
   - **Diária:** guarda o último backup de cada um dos últimos 7 dias.
   - **Semanal:** guarda o último backup de cada uma das últimas 4 semanas de calendário (semanas ISO, de segunda a domingo, incluindo a atual).
   - **Resto:** o resto é apagado (`.dump` e `.counts`).

**Limitação:** o `pg_dump` e as contagens correm em transações diferentes. Se houver escritas entre os dois, o `.counts` pode não bater com o dump e o `verify.sh` dá um falso alarme. Os backups devem correr numa altura sem escritas, ou numa réplica.

### Uma correção que o teste da tarefa 3 obrigou a fazer

A primeira versão usava "semanas" como janelas de 7 dias que acabam hoje (`[hoje-6, hoje]`, `[hoje-13, hoje-7]`, ...). Na simulação de 40 dias ficaram só 8 ficheiros e nenhum backup semanal antigo. Como a retenção corre todos os dias, as janelas andam um dia de cada vez. O backup "semanal" de uma janela passa no dia seguinte para outra janela, onde há um mais recente, e é apagado. Isto repete-se até não sobrar nenhum.

Com semanas de calendário fixas, o último backup de cada semana (normalmente o de domingo) fica o mesmo até essa semana sair das últimas 4.

## Tarefa 2: `verify.sh`

1. Escolhe o dump mais recente (os nomes ordenam por data e hora) e o `.counts` com o mesmo nome.
2. Arranca um contentor novo `postgres:18`, sem volume e sem nenhuma ligação ao ambiente do módulo, e espera que aceite ligações.
3. `pg_restore --no-owner --no-acl --exit-on-error`. Se o restauro falhar, sai com 1.
4. Conta as linhas de cada tabela com a mesma consulta, junta as duas listas por nome de tabela (`join`) e mostra cada diferença, incluindo tabelas que faltam de um dos lados (`MISSING`).
5. Sai com 0 se tudo bater certo e com 1 se houver diferenças. Um `trap` para o contentor no fim, em qualquer caso.

### Um dump bom

```
$ exercises/10-backup/challenge/verify.sh
2026-10-29 14:31:37 verifying pagila_2026-10-29_1431.dump
restored in 3 s
OK: 70 tables, all counts match
$ echo $?
0
```

### Um dump alterado de propósito

O `.counts` original ficou junto de um dump de uma cópia do Pagila de onde foram apagados 1000 alugueres (e os seus pagamentos) e 10 atores (e as suas ligações a filmes):

```bash
docker compose exec -T postgres createdb -U postgres pagila_changed -T pagila
docker compose exec -T postgres psql -U postgres -d pagila_changed -c "
  DELETE FROM payment WHERE rental_id IN (SELECT rental_id FROM rental ORDER BY rental_id DESC LIMIT 1000);
  DELETE FROM rental WHERE rental_id IN (SELECT rental_id FROM rental ORDER BY rental_id DESC LIMIT 1000);
  DELETE FROM film_actor WHERE actor_id > 190;
  DELETE FROM actor WHERE actor_id > 190;"
docker compose exec -T postgres pg_dump -U postgres -Fc pagila_changed > backups/verify_test/pagila_2026-10-29_0900.dump
```

```
$ BACKUP_DIR=backups/verify_test exercises/10-backup/challenge/verify.sh
2026-10-29 14:32:02 verifying pagila_2026-10-29_0900.dump
restored in 3 s
DIFFERENCES:
  actor                        expected 200      restored 190
  film_actor                   expected 5462     restored 5193
  payment                      expected 51061    restored 50088
  payment_p2026_06             expected 727      restored 566
  payment_p2026_07             expected 812      restored 0
  rental                       expected 51805    restored 50805
FAILED: 6 of 70 tables differ
$ echo $?
1
```

### Um dump corrompido (cortado aos 2 MB)

```
$ BACKUP_DIR=backups/verify_test exercises/10-backup/challenge/verify.sh
2026-10-29 14:32:19 verifying pagila_2026-10-29_0901.dump
pg_restore: error: could not read from input file: end of file
RESTORE FAILED
$ echo $?
1
```

## Tarefa 3: retenção em 40 dias simulados

Um backup por dia às 02:00, de 2026-09-20 a 2026-10-29 (40 dias). Nos dias 27, 28 e 29 houve um segundo backup às 23:00, para testar que fica o **último** de cada dia:

```bash
export BACKUP_DIR=backups/retention_test
for i in $(seq 39 -1 0); do
  d=$(date -d "2026-10-29 - $i days" +%F)
  exercises/10-backup/challenge/backup.sh --now $d 02:00
  case $d in 2026-10-27|2026-10-28|2026-10-29) exercises/10-backup/challenge/backup.sh --now $d 23:00;; esac
done
```

43 backups criados e 34 apagados. Ficheiros que restam (cada `.dump` tem o seu `.counts`, 9 de cada):

```
pagila_2026-10-11_0200.dump  Sun 2026-W41
pagila_2026-10-18_0200.dump  Sun 2026-W42
pagila_2026-10-23_0200.dump  Fri 2026-W43
pagila_2026-10-24_0200.dump  Sat 2026-W43
pagila_2026-10-25_0200.dump  Sun 2026-W43
pagila_2026-10-26_0200.dump  Mon 2026-W44
pagila_2026-10-27_2300.dump  Tue 2026-W44
pagila_2026-10-28_2300.dump  Wed 2026-W44
pagila_2026-10-29_2300.dump  Thu 2026-W44
```

| Regra | Ficheiros guardados |
|-------|---------------------|
| Último de cada um dos últimos 7 dias (23 a 29 de outubro) | 10-23, 10-24, 10-25, 10-26, **10-27_2300**, **10-28_2300**, **10-29_2300** (os das 02:00 desses três dias foram apagados) |
| Último de cada uma das últimas 4 semanas ISO | W44: 10-29_2300 (já guardado), W43: 10-25 (já guardado), W42: **10-18**, W41: **10-11** |

São 7 diários e 4 semanais. Dois semanais coincidem com diários, por isso ficam 9 ficheiros: exatamente os esperados. Tudo de antes de 2026-10-05 (início da W41) foi apagado.

## Tarefa 4: agendamento

### Configuração

**Linux e macOS (cron)**, com `crontab -e`:

```cron
# Backup e verificação todos os dias às 02:00. Ajustar o caminho do repositório.
0 2 * * * cd /caminho/para/databases_module && exercises/10-backup/challenge/backup.sh >> backups/pagila/cron.log 2>&1 && exercises/10-backup/challenge/verify.sh >> backups/pagila/cron.log 2>&1
```

**Windows (Task Scheduler)**, numa linha de comandos:

```bat
schtasks /Create /TN "pagila-backup" /SC DAILY /ST 02:00 /TR "\"C:\Program Files\Git\bin\bash.exe\" -lc 'cd /c/Users/<user>/projects/databases_module && INTERVAL=1 RUNS=1 exercises/10-backup/challenge/schedule.sh'"
```

**Windows sem Task Scheduler, ou WSL (ciclo):** `schedule.sh` corre `backup.sh` e depois `verify.sh` a cada `INTERVAL` segundos, `RUNS` vezes (0 = para sempre), e acrescenta tudo a `backups/pagila/schedule.log`:

```bash
INTERVAL=86400 RUNS=0 nohup exercises/10-backup/challenge/schedule.sh &   # uma vez por dia
```

### Log de duas execuções agendadas

Para não esperar dois dias, a demonstração usou o ciclo com um intervalo de 1 minuto (`INTERVAL=60 RUNS=2 exercises/10-backup/challenge/schedule.sh`). Não deixei nenhuma tarefa permanente instalada no sistema.

```
=== run 1 started 2026-10-29 14:42:01
2026-10-29 14:42:02 backup pagila_2026-10-29_1442.dump (4601357 bytes, 70 tables)
2026-10-29 14:42:04 retention: deleted pagila_2026-10-29_1431.dump
2026-10-29 14:42:04 verifying pagila_2026-10-29_1442.dump
restored in 3 s
OK: 70 tables, all counts match
=== run 1 finished 2026-10-29 14:42:13 with exit code 0
=== run 2 started 2026-10-29 14:43:13
2026-10-29 14:43:15 backup pagila_2026-10-29_1443.dump (4601357 bytes, 70 tables)
2026-10-29 14:43:16 retention: deleted pagila_2026-10-29_1442.dump
2026-10-29 14:43:16 verifying pagila_2026-10-29_1443.dump
restored in 3 s
OK: 70 tables, all counts match
=== run 2 finished 2026-10-29 14:43:25 with exit code 0
```

Cada execução faz o backup, aplica a retenção e verifica o backup acabado de fazer. A retenção apaga o backup anterior porque é do mesmo dia e só fica o último de cada dia. Cada ciclo completo demora cerca de 12 segundos.
