#!/usr/bin/env bash
# Tarefa 4: upgrade head, downgrade base e upgrade head outra vez, com
# \d customer e \d rental depois de cada passo.
# Correr a partir desta pasta, com DATABASE_URL a apontar para ex12.
set -euo pipefail

ROOT="$(cd ../../.. && pwd)"
describe() {
    (cd "$ROOT" && docker compose exec -T postgres psql -U postgres -d ex12 \
        -c '\d customer' -c '\d rental' \
        -c "SELECT customer_id, loyalty_points FROM customer WHERE customer_id = 1" 2>&1 || true)
}

for step in "upgrade head" "downgrade base" "upgrade head"; do
    echo "################ alembic $step ################"
    uv run alembic $step
    uv run alembic current
    describe
done
