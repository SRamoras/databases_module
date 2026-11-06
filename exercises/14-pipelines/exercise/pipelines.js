// Exercício 14: os 4 pipelines de agregação, sobre pagila_docs carregada pelo
// load.py do exercício 13 e sem alterações.
//   docker compose exec -T mongo mongosh -u root -p <password> --authenticationDatabase admin \
//       --quiet pagila_docs --eval "$(cat exercises/14-pipelines/exercise/pipelines.js)"

function show(label, docs, n = 5) {
  print(`\n=== ${label}: ${docs.length} documentos`);
  docs.slice(0, n).forEach((d) => print(EJSON.stringify(d, { relaxed: true })));
}

// 1. Receita por categoria por mês em 2025, por rental_date, a partir de rentals.
//    Um filme pode ter várias categorias: o aluguer conta para cada uma ($unwind).
const revenue = db.rentals.aggregate([
  // $match primeiro: só os alugueres de 2025 passam aos estágios seguintes
  { $match: { rental_date: { $gte: ISODate("2025-01-01T00:00:00Z"), $lt: ISODate("2026-01-01T00:00:00Z") } } },
  { $unwind: "$categories" },
  {
    $group: {
      _id: {
        category: "$categories",
        month: { $dateToString: { date: "$rental_date", format: "%Y-%m", timezone: "UTC" } },
      },
      revenue: { $sum: "$amount" },
    },
  },
  { $project: { _id: 0, category: "$_id.category", month: "$_id.month", revenue: 1 } },
  { $sort: { category: 1, month: 1 } },
]).toArray();
show("1. receita por categoria por mês (2025)", revenue);
show("1. Action, janeiro de 2025",
  revenue.filter((d) => d.category === "Action" && d.month === "2025-01"));

// 2. O ator com mais filmes em cada categoria, com empates.
const topActors = db.films.aggregate([
  { $unwind: "$categories" },
  { $unwind: "$actors" },
  {
    $group: {
      _id: { category: "$categories", actor_id: "$actors.actor_id" },
      name: { $first: "$actors.name" },
      films: { $sum: 1 },
    },
  },
  // $rank dá o mesmo lugar aos empatados, por isso rank 1 inclui os empates
  {
    $setWindowFields: {
      partitionBy: "$_id.category",
      sortBy: { films: -1 },
      output: { rank: { $rank: {} } },
    },
  },
  { $match: { rank: 1 } },
  { $sort: { "_id.actor_id": 1 } },
  {
    $group: {
      _id: "$_id.category",
      films: { $first: "$films" },
      actors: { $push: { actor_id: "$_id.actor_id", name: "$name" } },
    },
  },
  { $project: { _id: 0, category: "$_id", films: 1, actors: 1 } },
  { $sort: { category: 1 } },
]).toArray();
show("2. ator com mais filmes por categoria", topActors, 16);
print(`atores no total: ${topActors.reduce((n, d) => n + d.actors.length, 0)}`);

// 3. Distribuição das durações
const lengths = db.films.aggregate([
  {
    $bucket: {
      groupBy: "$length",
      boundaries: [0, 60, 90, 120, 150, 186],
      output: { films: { $sum: 1 } },
    },
  },
]).toArray();
show("3. $bucket das durações", lengths);

// 4. Três resumos numa só passagem por films
const RATINGS = ["G", "PG", "PG-13", "R", "NC-17"];
const summary = db.films.aggregate([
  {
    $facet: {
      totals: [
        { $group: { _id: null, films: { $sum: 1 }, avg_rental_rate: { $avg: "$rental_rate" } } },
        { $project: { _id: 0, films: 1, avg_rental_rate: { $round: ["$avg_rental_rate", 2] } } },
      ],
      by_rating: [
        { $group: { _id: "$rating", films: { $sum: 1 } } },
        { $set: { order: { $indexOfArray: [RATINGS, "$_id"] } } },
        { $sort: { order: 1 } },
        { $project: { _id: 0, rating: "$_id", films: 1 } },
      ],
      longest: [
        { $sort: { length: -1, title: 1 } },
        { $limit: 5 },
        { $project: { _id: 0, title: 1, length: 1 } },
      ],
    },
  },
]).toArray();
print(`\n=== 4. $facet: ${summary.length} documento`);
print(EJSON.stringify(summary[0], null, 2, { relaxed: true }));
