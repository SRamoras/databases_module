# Exercício 10: Backup, incidente e restauro

| Ficheiro | Conteúdo |
|----------|----------|
| [`runbook.md`](runbook.md) | **A entrega principal.** Quando usar, pré-requisitos, todos os comandos por ordem, contagens das tarefas 1, 3 e 5, RTO e RPO medidos, verificação e melhorias à estratégia de backups. |
| `activity.sql` | O trabalho normal depois do backup (igual ao enunciado) |
| `disaster.sql` | O incidente (igual ao enunciado) |
| `counts.sql` | Contagens de `payment`, `film_actor`, `film_category` e dos pagamentos de 2026 |
| `verify.sql` | Comparação linha a linha das três tabelas com uma cópia restaurada do backup |

Os backups vão para `backups/` na raiz do repositório, que está no `.gitignore` (tal como `*.dump`), por isso não são submetidos.

## Resumo

| Tabela | Antes | Depois do incidente | Depois do restauro |
|--------|-------|---------------------|--------------------|
| `payment` | 51 061 | 45 780 | 51 061 |
| `film_actor` | 5 462 | 4 135 | 5 462 |
| `film_category` | 2 367 | 2 218 | 2 367 |

- **Restauro:** sem apagar a base de dados, numa só transação (`TRUNCATE` das duas tabelas parciais e recarga, mais as 7 partições de 2026). Demorou **0,54 s**.
- **Verificação:** 0 diferenças linha a linha nas três tabelas, comparando com o backup.
- **Perdido (RPO):** os **5 pagamentos do `activity.sql`** (IDs 102095 a 102099), feitos depois do backup.
