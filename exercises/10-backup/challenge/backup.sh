#!/usr/bin/env bash
# Backup de pagila em formato custom, com contagens e retenção.
#
# Uso: backup.sh [--now YYYY-MM-DD [HH:MM]]
#   --now   substitui a data (e opcionalmente a hora) atual, para testar a retenção sem esperar semanas.
#
# Cria, em $BACKUP_DIR (por omissão backups/pagila na raiz do repositório):
#   pagila_YYYY-MM-DD_HHMM.dump     pg_dump -Fc
#   pagila_YYYY-MM-DD_HHMM.counts   "tabela|linhas" de cada tabela no momento do dump
# Depois aplica a retenção: guarda o último backup de cada um dos últimos 7 dias e o último de
# cada uma das últimas 4 semanas de calendário (semanas ISO, de segunda a domingo, incluindo a
# atual); apaga o resto.
set -euo pipefail
export MSYS_NO_PATHCONV=1  # Git Bash no Windows: não converter argumentos que parecem caminhos

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
set -a; source .env; set +a

DB=pagila
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups/pagila}"

today=$(date +%F)
hhmm=$(date +%H%M)
if [ "${1:-}" = "--now" ]; then
    today="${2:?--now precisa de YYYY-MM-DD}"
    date -d "$today" +%F > /dev/null  # falha se a data for inválida
    if [ -n "${3:-}" ]; then hhmm="${3/:/}"; fi
fi

mkdir -p "$BACKUP_DIR"
name="pagila_${today}_${hhmm}"

# Contagens de todas as tabelas (inclui as partições e a tabela particionada payment).
COUNT_SQL="SELECT table_name || '|' ||
       (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM public.%I', table_name), false, true, '')))[1]::text
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
ORDER BY table_name;"

# Dump e contagens dentro da mesma transação REPEATABLE READ não é possível com pg_dump a partir de
# fora, por isso a base de dados não deve receber escritas durante o backup (ver README).
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -Fc "$DB" > "$BACKUP_DIR/$name.dump.tmp"
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$DB" -At -v ON_ERROR_STOP=1 -c "$COUNT_SQL" > "$BACKUP_DIR/$name.counts.tmp"
mv "$BACKUP_DIR/$name.dump.tmp" "$BACKUP_DIR/$name.dump"
mv "$BACKUP_DIR/$name.counts.tmp" "$BACKUP_DIR/$name.counts"
echo "$(date '+%F %T') backup $name.dump ($(wc -c < "$BACKUP_DIR/$name.dump") bytes, $(wc -l < "$BACKUP_DIR/$name.counts") tables)"

# --- Retenção --------------------------------------------------------------------------------
# Os nomes ordenam por data e hora, por isso o último de um intervalo é o maior nome dentro dele.
# As semanas são de calendário e não "os 7 dias até hoje": com janelas que andam um dia de cada
# vez, o backup semanal de ontem cai noutra janela no dia seguinte e é apagado, e nenhum semanal
# chega a sobreviver. Com semanas fixas, o último backup de cada semana fica estável.
keep=()
backup_day() { basename "$1" | sed -E 's/^pagila_([0-9-]{10})_.*/\1/'; }
latest_where() {  # $1 = formato de date (+%F para o dia, +%G-W%V para a semana ISO), $2 = valor
    local best=""
    for f in "$BACKUP_DIR"/pagila_*.dump; do
        [ -e "$f" ] || continue
        if [ "$(date -d "$(backup_day "$f")" "$1")" = "$2" ]; then best="$f"; fi
    done
    [ -n "$best" ] && keep+=("$best")
    return 0
}

for i in 0 1 2 3 4 5 6; do                          # últimos 7 dias
    latest_where +%F "$(date -d "$today - $i days" +%F)"
done
for w in 0 1 2 3; do                                # últimas 4 semanas ISO (a atual e as 3 anteriores)
    latest_where +%G-W%V "$(date -d "$today - $((w * 7)) days" +%G-W%V)"
done

for f in "$BACKUP_DIR"/pagila_*.dump; do
    [ -e "$f" ] || continue
    if [[ ! " ${keep[*]} " == *" $f "* ]]; then
        rm -f "$f" "${f%.dump}.counts"
        echo "$(date '+%F %T') retention: deleted $(basename "$f")"
    fi
done
