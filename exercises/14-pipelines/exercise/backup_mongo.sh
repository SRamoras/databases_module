#!/usr/bin/env bash
# Faz o dump de pagila_docs para backups/ como um arquivo comprimido com a data no nome.
# Uso (de qualquer pasta): exercises/14-pipelines/exercise/backup_mongo.sh
set -euo pipefail

cd "$(dirname "$0")/../../.."          # raiz do repositório (onde estão .env e compose)
set -a; source .env; set +a

mkdir -p backups
file="backups/mongo_pagila_docs_$(date +%F_%H%M%S).archive.gz"

docker compose exec -T mongo mongodump \
    --uri "mongodb://${MONGO_ROOT_USER}:${MONGO_ROOT_PASSWORD}@localhost:27017/?authSource=admin" \
    --db pagila_docs --archive --gzip > "$file"

echo "Backup: $file ($(du -h "$file" | cut -f1))"
