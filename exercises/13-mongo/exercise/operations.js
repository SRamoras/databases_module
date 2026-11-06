// Tarefa 2: as 8 operações, para correr com mongosh sobre pagila_docs acabada de carregar.
//   docker compose exec -T mongo mongosh -u root -p <password> --authenticationDatabase admin \
//       --quiet pagila_docs --eval "$(cat exercises/13-mongo/exercise/operations.js)"
// As operações 6, 7 e 8 alteram dados: para as repetir, correr load.py outra vez
// (e apagar o filme 1001, que o load.py não conhece).

const show = (label, value) => print(`\n--- ${label}\n${EJSON.stringify(value)}`);

// 1. Filmes PG-13 com mais de 120 minutos
show("1. PG-13 e length > 120",
  db.films.countDocuments({ rating: "PG-13", length: { $gt: 120 } }));

// 2. Filmes em que entra o ator 1 (dot notation num array de documentos)
show("2. ator 1",
  db.films.countDocuments({ "actors.actor_id": 1 }));

// 3. Filmes de Horror com rental_rate 0.99. O valor tem de ser Decimal128:
//    o número 0.99 (double) não é igual a NumberDecimal("0.99").
show("3. Horror e rental_rate 0.99",
  db.films.countDocuments({ categories: "Horror", rental_rate: NumberDecimal("0.99") }));

// 4. Clientes com pelo menos um aluguer não devolvido em recent_rentals.
//    { return_date: null } também apanharia documentos sem o campo; com $elemMatch
//    a condição aplica-se a cada elemento do array.
show("4. clientes com aluguer aberto em recent_rentals",
  db.customers.countDocuments({ recent_rentals: { $elemMatch: { return_date: null } } }));

// 5. Cliente 1 com first_name, last_name e só os títulos de recent_rentals
const c1 = db.customers.findOne(
  { _id: 1 },
  { _id: 0, first_name: 1, last_name: 1, "recent_rentals.title": 1 }
);
show("5. projeção do cliente 1", c1);
show("5. número de títulos", c1.recent_rentals.length);

// 6. +0.50 no rental_rate dos filmes NC-17 com menos de 60 minutos
const r6 = db.films.updateMany(
  { rating: "NC-17", length: { $lt: 60 } },
  { $inc: { rental_rate: NumberDecimal("0.50") } }
);
show("6. updateMany $inc", { matched: r6.matchedCount, modified: r6.modifiedCount });

// 7. Um aluguer novo à cabeça de recent_rentals, ficando só com 10
const newRental = {
  rental_id: 90001,
  film_id: 1,
  title: "ACADEMY DINOSAUR",
  rental_date: new Date("2026-07-30T10:00:00Z"),
  return_date: null,
};
const r7 = db.customers.updateOne(
  { _id: 1 },
  { $push: { recent_rentals: { $each: [newRental], $position: 0, $slice: 10 } } }
);
const after7 = db.customers.findOne({ _id: 1 }, { recent_rentals: 1 });
show("7. $push com $each, $position e $slice", {
  modified: r7.modifiedCount,
  size: after7.recent_rentals.length,
  first: after7.recent_rentals[0].rental_id,
  last: after7.recent_rentals[9].rental_id,
});

// 8. Upsert com $setOnInsert, duas vezes
for (const run of [1, 2]) {
  const r8 = db.films.updateOne(
    { _id: 1001 },
    { $setOnInsert: { title: "TEST FILM" } },
    { upsert: true }
  );
  show(`8. upsert, execução ${run}`, {
    matched: r8.matchedCount,
    modified: r8.modifiedCount,
    upserted: r8.upsertedCount,
  });
}
