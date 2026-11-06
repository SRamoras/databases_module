// Tarefa 3: validação $jsonSchema em films, e duas inserções que têm de ser rejeitadas.
//   docker compose exec -T mongo mongosh -u root -p <password> --authenticationDatabase admin \
//       --quiet pagila_docs --eval "$(cat exercises/13-mongo/exercise/validation.js)"

const result = db.runCommand({
  collMod: "films",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["title", "rating", "length", "rental_rate", "categories", "actors"],
      properties: {
        title: { bsonType: "string" },
        rating: { enum: ["G", "PG", "PG-13", "R", "NC-17"] },
        length: { bsonType: "int", minimum: 1, maximum: 999 },
        rental_rate: { bsonType: "decimal" },
        categories: { bsonType: "array", items: { bsonType: "string" } },
        actors: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: ["actor_id", "name"],
            properties: {
              actor_id: { bsonType: "int" },
              name: { bsonType: "string" },
            },
          },
        },
      },
    },
  },
  validationLevel: "strict",
  validationAction: "error",
});
print(`collMod: ${EJSON.stringify(result)}`);

// Um filme válido, de que cada teste muda um só campo
const valid = {
  title: "VALIDATION TEST",
  rating: "PG",
  length: 90,
  rental_rate: NumberDecimal("2.99"),
  categories: ["Drama"],
  actors: [{ actor_id: 1, name: "PENELOPE GUINESS" }],
};

for (const [label, doc] of [
  ['rating: "XXX"', { ...valid, _id: 9001, rating: "XXX" }],
  ['length: "long"', { ...valid, _id: 9002, length: "long" }],
]) {
  try {
    db.films.insertOne(doc);
    print(`\n${label}: ACEITE (não devia)`);
  } catch (e) {
    print(`\n${label}: rejeitado, ${e.name} (code ${e.code}): ${e.errmsg}`);
    print(EJSON.stringify(e.errInfo.details.schemaRulesNotSatisfied));
  }
}
