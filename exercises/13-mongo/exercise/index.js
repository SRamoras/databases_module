// Tarefa 4: explain antes e depois de um índice multikey em actors.actor_id.
//   docker compose exec -T mongo mongosh -u root -p <password> --authenticationDatabase admin \
//       --quiet pagila_docs --eval "$(cat exercises/13-mongo/exercise/index.js)"

function summary(label) {
  const ex = db.films.find({ "actors.actor_id": 1 }).explain("executionStats");
  // O plano é uma árvore: FETCH -> IXSCAN, ou só COLLSCAN
  const stages = [];
  for (let s = ex.queryPlanner.winningPlan.queryPlan ?? ex.queryPlanner.winningPlan; s; s = s.inputStage) {
    stages.push(s.stage + (s.indexName ? ` (${s.indexName}, isMultiKey: ${s.isMultiKey})` : ""));
  }
  const st = ex.executionStats;
  print(`\n${label}`);
  print(`  stage:             ${stages.join(" <- ")}`);
  print(`  totalKeysExamined: ${st.totalKeysExamined}`);
  print(`  totalDocsExamined: ${st.totalDocsExamined}`);
  print(`  nReturned:         ${st.nReturned}`);
  print(`  executionTimeMillis: ${st.executionTimeMillis}`);
}

// Para o "antes" ser mesmo sem índice, mesmo que o script já tenha corrido
try { db.films.dropIndex("actors.actor_id_1"); } catch (e) { /* ainda não existia */ }
summary("Antes do índice");
print(`\ncreateIndex: ${db.films.createIndex({ "actors.actor_id": 1 })}`);
summary("Depois do índice");
