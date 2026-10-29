#!/usr/bin/env bash
# Agendamento por ciclo, para Windows (Git Bash / WSL) sem cron nem Task Scheduler.
# Corre backup.sh e verify.sh a cada INTERVAL segundos, RUNS vezes (0 = para sempre),
# e acrescenta tudo a $LOG (por omissão backups/pagila/schedule.log).
#
# Uso: INTERVAL=86400 RUNS=0 ./schedule.sh      # uma vez por dia, para sempre
#      INTERVAL=60 RUNS=2 ./schedule.sh         # demonstração: duas execuções com 1 minuto de intervalo
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/../../.." && pwd)"
INTERVAL="${INTERVAL:-86400}"
RUNS="${RUNS:-0}"
LOG="${LOG:-$ROOT/backups/pagila/schedule.log}"
mkdir -p "$(dirname "$LOG")"

run=0
while :; do
    run=$((run + 1))
    {
        echo "=== run $run started $(date '+%F %T')"
        "$DIR/backup.sh" && "$DIR/verify.sh"
        echo "=== run $run finished $(date '+%F %T') with exit code $?"
    } >> "$LOG" 2>&1
    if [ "$RUNS" -ne 0 ] && [ "$run" -ge "$RUNS" ]; then break; fi
    sleep "$INTERVAL"
done
