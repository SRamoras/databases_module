#!/usr/bin/env bash
# Restaura o arquivo mais recente de backups/ para a base de dados pagila_docs_restored
# e mostra o número de documentos de cada coleção nas duas bases de dados.
# Uso (de qualquer pasta): exercises/14-pipelines/exercise/restore_mongo.sh
set -euo pipefail

cd "$(dirname "$0")/../../.."
set -a; source .env; set +a

uri="mongodb://${MONGO_ROOT_USER}:${MONGO_ROOT_PASSWORD}@localhost:27017/?authSource=admin"
latest="$(ls -t backups/mongo_pagila_docs_*.archive.gz 2>/dev/null | head -1)"
if [ -z "$latest" ]; then
    echo "Nenhum backup em backups/. Correr primeiro backup_mongo.sh." >&2
    exit 1
fi
echo "A restaurar $latest para pagila_docs_restored"

# --nsFrom/--nsTo mudam o nome da base de dados; --drop substitui as coleções que já existam
docker compose exec -T mongo mongorestore --uri "$uri" \
    --archive --gzip --drop \
    --nsFrom 'pagila_docs.*' --nsTo 'pagila_docs_restored.*' < "$latest"

docker compose exec -T mongo mongosh "$uri" --quiet --eval '
  const orig = db.getSiblingDB("pagila_docs");
  const rest = db.getSiblingDB("pagila_docs_restored");
  let ok = true;
  print("\ncoleção      pagila_docs  pagila_docs_restored");
  for (const name of orig.getCollectionNames().sort()) {
    const a = orig[name].countDocuments({});
    const b = rest[name].countDocuments({});
    if (a !== b) ok = false;
    print(`${name.padEnd(12)} ${String(a).padStart(11)}  ${String(b).padStart(20)}`);
  }
  print(ok ? "\nOK: contagens iguais" : "\nDIFERENTE");
  if (!ok) quit(1);
'
