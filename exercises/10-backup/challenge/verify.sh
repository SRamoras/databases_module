#!/usr/bin/env bash
# Verifica o último backup restaurando-o num contentor descartável e comparando as contagens.
#
# Uso: verify.sh [ficheiro.dump]
#   Sem argumento usa o dump mais recente de $BACKUP_DIR (por omissão backups/pagila).
# Sai com 0 se todas as contagens forem iguais às do ficheiro .counts do dump, e com 1 se houver
# alguma diferença ou se o restauro falhar.
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups/pagila}"

dump="${1:-$(ls "$BACKUP_DIR"/pagila_*.dump 2>/dev/null | sort | tail -1)}"
[ -n "$dump" ] && [ -f "$dump" ] || { echo "no dump found in $BACKUP_DIR"; exit 1; }
counts="${dump%.dump}.counts"
[ -f "$counts" ] || { echo "missing $counts"; exit 1; }
echo "$(date '+%F %T') verifying $(basename "$dump")"

# Contentor novo, sem volume: não depende de nada do ambiente do módulo, e desaparece no fim.
container="pg-verify-$$"
docker run --rm -d --name "$container" -e POSTGRES_PASSWORD=verify postgres:18 > /dev/null
trap 'docker stop "$container" > /dev/null 2>&1 || true' EXIT

for _ in $(seq 60); do
    docker exec "$container" pg_isready -U postgres -q 2>/dev/null && break
    sleep 1
done
# pg_isready responde durante o arranque inicial; espera pela instância definitiva.
until docker exec "$container" psql -U postgres -Atc "SELECT 1" > /dev/null 2>&1; do sleep 1; done

docker exec "$container" createdb -U postgres pagila
start=$(date +%s)
if ! docker exec -i "$container" pg_restore -U postgres -d pagila --no-owner --no-acl --exit-on-error < "$dump"; then
    echo "RESTORE FAILED"
    exit 1
fi
echo "restored in $(( $(date +%s) - start )) s"

COUNT_SQL="SELECT table_name || '|' ||
       (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM public.%I', table_name), false, true, '')))[1]::text
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
ORDER BY table_name;"
actual=$(docker exec "$container" psql -U postgres -d pagila -At -v ON_ERROR_STOP=1 -c "$COUNT_SQL" | tr -d '\r')
expected=$(tr -d '\r' < "$counts")

# Junta as duas listas por nome de tabela e mostra cada diferença.
differences=$(join -t '|' -a 1 -a 2 -e MISSING -o 0,1.2,2.2 \
    <(echo "$expected" | sort -t '|' -k 1,1) <(echo "$actual" | sort -t '|' -k 1,1) |
    awk -F '|' '$2 != $3 { printf "  %-28s expected %-8s restored %s\n", $1, $2, $3 }')

tables=$(echo "$expected" | wc -l)
if [ -n "$differences" ]; then
    echo "DIFFERENCES:"
    echo "$differences"
    echo "FAILED: $(echo "$differences" | wc -l) of $tables tables differ"
    exit 1
fi
echo "OK: $tables tables, all counts match"
