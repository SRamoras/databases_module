# Runbook: recuperar linhas apagadas de `payment`, `film_actor` e `film_category` a partir de um backup

## Quando usar

Usar este runbook quando foram apagadas por engano (ou por um incidente) linhas de `payment`, `film_actor` e/ou `film_category` numa base de dados Pagila, a base de dados continua a funcionar, e existe um backup em formato custom (`pg_dump -Fc`) anterior ao incidente.

**Não usar** se:
- a base de dados está corrompida ou não arranca. Aí é preciso restaurar a base de dados inteira, como no tutorial da sessão 10.
- o backup é posterior ao incidente. Nesse caso o backup já não tem as linhas apagadas.

Este procedimento **não apaga nem recria a base de dados**: só repõe os dados das tabelas afetadas, e o resto da base de dados continua em uso.

## Pré-requisitos

- O ambiente do módulo a correr: `docker compose ps` mostra o `postgres` `healthy`.
- Acesso à pasta `backups/` na raiz do repositório e à palavra-passe do `postgres` (`.env` na raiz).
- O backup mais recente **anterior** ao incidente. Para confirmar a hora a que foi feito:
  ```bash
  docker compose exec -T postgres pg_restore --list < backups/<ficheiro>.dump | head -3
  # ; Archive created at 2026-10-29 14:28:32 UTC
  ```
- Saber que linhas foram apagadas. Neste incidente foi o `disaster.sql`:
  - `payment` com `payment_date >= '2026-01-01'` (partições `payment_p2026_01` a `payment_p2026_07`);
  - `film_actor` com `actor_id <= 50`;
  - `film_category` com `category_id = 1`.
- Combinar com a equipa uma janela sem escritas nestas tabelas durante o restauro (cerca de 1 minuto). Ver "Riscos".

Todos os comandos correm a partir da raiz do repositório. Em todo o documento, `DUMP` é o ficheiro do backup:

```bash
DUMP=backups/ex10_2026-10-29_1428.dump
```

## Procedimento

### 0. Como o incidente foi reproduzido (só para o exercício)

```bash
./scripts/create-db.sh ex10 --pagila --reset

# Tarefa 1: contagens antes de tudo
docker compose exec -T postgres psql -U postgres -d ex10 < exercises/10-backup/exercise/counts.sql

# Tarefa 2: backup em formato custom
mkdir -p backups
docker compose exec -T postgres pg_dump -U postgres -Fc ex10 > backups/ex10_$(date -u +%F_%H%M).dump

# Tarefa 3: trabalho normal depois do backup, e o incidente
docker compose exec -T postgres psql -U postgres -d ex10 -v ON_ERROR_STOP=1 < exercises/10-backup/exercise/activity.sql
docker compose exec -T postgres psql -U postgres -d ex10 -v ON_ERROR_STOP=1 < exercises/10-backup/exercise/disaster.sql
docker compose exec -T postgres psql -U postgres -d ex10 < exercises/10-backup/exercise/counts.sql
```

### 1. Registar o estado atual

Antes de mexer em qualquer coisa, registar as contagens e o próximo `payment_id` (a sequência não volta atrás com o restauro, por isso é com ela que se mede o RPO no passo 5):

```bash
docker compose exec -T postgres psql -U postgres -d ex10 < exercises/10-backup/exercise/counts.sql
docker compose exec -T postgres psql -U postgres -d ex10 -c "SELECT last_value FROM payment_payment_id_seq;"
```

### 2. Confirmar que o backup tem os dados das tabelas a restaurar

```bash
docker compose exec -T postgres pg_restore --list < $DUMP | grep "TABLE DATA" | grep -E "film_actor|film_category|payment_p2026"
```

Têm de aparecer 9 linhas: `film_actor`, `film_category` e `payment_p2026_01` a `payment_p2026_07`.

`payment` é uma tabela particionada: as linhas estão guardadas nas partições, por isso cada partição tem de ser indicada pelo nome. `-t payment` sozinho não restaura nada.

### 3. Restaurar, numa só transação

```bash
time ( {
  echo "TRUNCATE film_actor, film_category;"
  docker compose exec -T postgres pg_restore --data-only \
    -t film_actor -t film_category \
    -t payment_p2026_01 -t payment_p2026_02 -t payment_p2026_03 -t payment_p2026_04 \
    -t payment_p2026_05 -t payment_p2026_06 -t payment_p2026_07 \
    -f - < $DUMP
} | docker compose exec -T postgres psql -U postgres -d ex10 --single-transaction -v ON_ERROR_STOP=1 -q )
```

O que faz:

| Parte | Porquê |
|-------|--------|
| `pg_restore --data-only -t ... -f -` | Não restaura nada diretamente: escreve o SQL com os dados (`COPY ... FROM stdin`) das 9 tabelas indicadas. `--data-only` não toca na estrutura: as tabelas, índices, vistas e restrições continuam como estão. |
| `TRUNCATE film_actor, film_category` | Estas duas tabelas ainda têm parte das linhas. Recarregá-las por cima dava erro de chave primária duplicada. Esvaziam-se e recarregam-se inteiras a partir do backup. Não é preciso `CASCADE`, porque nenhuma tabela tem chaves estrangeiras para elas. |
| As partições de 2026 **não** levam `TRUNCATE` | Estão vazias depois do incidente. Assim, se alguém tiver entretanto inserido pagamentos novos de 2026, eles ficam. Se algum tiver o mesmo `payment_id` de uma linha do backup, o restauro falha (ver "Riscos"). |
| `psql --single-transaction -v ON_ERROR_STOP=1` | O `TRUNCATE` e as 9 cargas correm numa única transação. Se alguma coisa falhar, o `psql` para e o PostgreSQL desfaz **tudo**, incluindo o `TRUNCATE`. Nunca fica uma tabela vazia a meio do restauro. |

Saída esperada: um `set_config` vazio (do cabeçalho do SQL do `pg_restore`), sem `ERROR`, e código de saída 0.

### 4. Verificar o restauro

**a) Contagens** (têm de ser iguais às de antes do incidente):

```bash
docker compose exec -T postgres psql -U postgres -d ex10 < exercises/10-backup/exercise/counts.sql
```

**b) Comparação linha a linha com o backup.** Restaurar o mesmo dump inteiro numa base de dados à parte e comparar as três tabelas com `EXCEPT` nos dois sentidos:

```bash
docker compose exec -T postgres dropdb -U postgres --if-exists ex10_verify
docker compose exec -T postgres createdb -U postgres ex10_verify
docker compose exec -T postgres pg_restore -U postgres -d ex10_verify --no-owner < $DUMP
docker compose exec -T postgres psql -U postgres -d ex10 -q -v ON_ERROR_STOP=1 < exercises/10-backup/exercise/verify.sql
docker compose exec -T postgres dropdb -U postgres ex10_verify
```

Resultado esperado: `0` e `0` nas três linhas. `verify.sql` usa `postgres_fdw` para ler `ex10_verify` a partir de `ex10`, e apaga o que criou no fim.

**c) As linhas que o incidente apagou voltaram.** Têm de dar 1327, 149 e 5281 (os números do `DELETE` do incidente, sem os 5 pagamentos perdidos):

```bash
docker compose exec -T postgres psql -U postgres -d ex10 \
  -c "SELECT count(*) FROM film_actor WHERE actor_id <= 50;" \
  -c "SELECT count(*) FROM film_category WHERE category_id = 1;" \
  -c "SELECT count(*) FROM payment WHERE payment_date >= '2026-01-01';"
```

### 5. Medir o que se perdeu (RPO)

Tudo o que foi escrito entre o backup e o incidente não está no backup, por isso não volta. Para `payment`, a sequência mostra os IDs atribuídos depois do backup:

```bash
docker compose exec -T postgres psql -U postgres -d ex10 -c "
SELECT g AS lost_payment_id
FROM generate_series((SELECT max(payment_id) + 1 FROM payment),
                     (SELECT last_value FROM payment_payment_id_seq)) AS g;"
```

Para este incidente também se pode confirmar pelo conteúdo do `activity.sql`: os 5 alugueres mais recentes ficaram sem o pagamento de 1.99:

```bash
docker compose exec -T postgres psql -U postgres -d ex10 -c "
SELECT r.rental_id, r.customer_id, p.payment_id
FROM (SELECT rental_id, customer_id FROM rental ORDER BY rental_id DESC LIMIT 5) r
LEFT JOIN payment p ON p.rental_id = r.rental_id AND p.amount = 1.99 AND p.payment_date = '2026-07-30 12:00+00'
ORDER BY r.rental_id DESC;"
```

### 6. Comunicar

Depois do restauro, avisar:
- **Equipa responsável pela aplicação/plataforma:** que o restauro terminou e que as escritas podem continuar.
- **Quem trata dos pagamentos (financeiro, apoio ao cliente):** a lista dos pagamentos perdidos (passo 5), com cliente, aluguer e valor, para os voltarem a registar a partir de outra fonte (recibos, sistema de pagamentos).
- **Responsável do incidente:** este runbook preenchido (hora do backup, hora do incidente, RTO e RPO medidos).

## Resultados deste incidente

### Contagens

| Tabela | Tarefa 1: antes | Tarefa 3: depois do incidente | Tarefa 5: depois do restauro |
|--------|-----------------|-------------------------------|------------------------------|
| `payment` | 51 061 | 45 780 | **51 061** |
| `film_actor` | 5 462 | 4 135 | **5 462** |
| `film_category` | 2 367 | 2 218 | **2 367** |
| `payment` de 2026 | 5 281 | 0 | **5 281** |

Output do `disaster.sql`:

```
BEGIN
DELETE 5286
DELETE 1327
DELETE 149
COMMIT
```

O `DELETE` de `payment` apagou 5 286 linhas: as 5 281 de 2026 que estavam no backup e os 5 pagamentos inseridos pelo `activity.sql` depois do backup. Depois do restauro, as três tabelas têm exatamente as contagens da tarefa 1, e a comparação linha a linha com o backup dá 0 diferenças:

```
  table_name   | only_in_ex10 | only_in_backup
---------------+--------------+----------------
 payment       |            0 |              0
 film_actor    |            0 |              0
 film_category |            0 |              0
```

### Linha temporal

| Hora (UTC) | Acontecimento |
|------------|---------------|
| 14:28:32 | Backup `backups/ex10_2026-10-29_1428.dump` (4,6 MB, 0,76 s) |
| 14:28:34 | `activity.sql`: 5 pagamentos novos (IDs 102095 a 102099) |
| 14:28:34 | `disaster.sql` |

### RTO real (tempo de restauro)

| Passo | Tempo medido |
|-------|--------------|
| Restauro (passo 3) | **0,54 s** |
| Restauro do dump inteiro em `ex10_verify` (só para verificar) | 3,2 s |

O restauro em si demora menos de 1 segundo, porque só repõe 9 tabelas (~13 000 linhas). Na prática, o RTO de um incidente real é dominado pelo resto: perceber o que foi apagado, escolher o backup e verificar. Com este runbook, calculo cerca de **10 a 15 minutos** do alerta até à confirmação.

### RPO real (dados perdidos)

```
 lost_payment_id
-----------------
          102095
          102096
          102097
          102098
          102099
(5 rows)
```

```
 rental_id | customer_id | payment_id
-----------+-------------+------------
     87559 |           3 |
     87558 |         676 |
     87557 |         484 |
     87556 |         715 |
     87555 |         250 |
(5 rows)
```

**Perderam-se os 5 pagamentos do `activity.sql`** (IDs 102095 a 102099, 1.99 cada, aos alugueres 87555 a 87559). Foram feitos depois do backup e apagados pelo incidente, por isso não existem em nenhum lado. O RPO é o intervalo entre o backup e o incidente: neste exercício, 2 segundos e 5 linhas. Numa base de dados real com um backup diário, seria até um dia inteiro de pagamentos.

`film_actor` e `film_category` não perderam nada: não houve escritas nelas entre o backup e o incidente.

## Riscos e cuidados

- **Escritas durante o restauro.** O `TRUNCATE` bloqueia `film_actor` e `film_category` até ao fim da transação, por isso as leituras e escritas nessas tabelas esperam (menos de 1 s aqui). Uma linha inserida em `film_actor` ou `film_category` **entre o incidente e o restauro** é apagada pelo `TRUNCATE`. Se isso puder ter acontecido, usar a alternativa abaixo.
- **Pagamentos novos em 2026 depois do incidente.** Ficam, porque as partições não levam `TRUNCATE`. Mas um pagamento novo nunca reutiliza um `payment_id` do backup (a sequência só avança), por isso não há conflitos.
- **Alternativa sem `TRUNCATE`**, quando há escritas novas a preservar: restaurar o dump inteiro em `ex10_verify` (passo 4b) e copiar só as linhas em falta, com `postgres_fdw` e `INSERT INTO film_actor SELECT ... FROM verify.film_actor EXCEPT SELECT ... FROM film_actor`.

## O que mudaria na estratégia de backups para perder menos

1. **Arquivo contínuo do WAL e PITR (*point-in-time recovery*).** Com `archive_mode = on` e um backup base (`pg_basebackup`), é possível restaurar até ao segundo antes do incidente (por exemplo `recovery_target_time = '2026-10-29 14:28:33'`). Os 5 pagamentos do `activity.sql` voltavam. O RPO passa de "desde o último dump" para segundos. Ferramentas como pgBackRest ou WAL-G tratam disto.
2. **Dumps mais frequentes e verificados.** Enquanto não há PITR, um `pg_dump` de hora a hora limita a perda a uma hora. Cada dump deve ser verificado com um restauro automático (o desafio desta sessão).
3. **Cópias fora da máquina.** `backups/` está no mesmo disco que a base de dados. Os dumps (e o WAL arquivado) devem ir também para outro sítio, por exemplo um armazenamento de objetos com retenção e proteção contra apagamento.
4. **Prevenir o incidente.** O `disaster.sql` correu com o superutilizador. A aplicação deve usar um role sem `DELETE` em massa (sessão 09), e as alterações manuais devem seguir o padrão da sessão 04: `SELECT count(*)` com o mesmo `WHERE` antes do `DELETE`, dentro de uma transação. Um `DELETE` em `payment` também podia ser registado numa tabela de auditoria por trigger, para que as linhas apagadas pudessem ser recuperadas sem backup.
