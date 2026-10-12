const test = require("node:test");
const assert = require("node:assert/strict");
const {
  PERSONAS,
  createSeededRandom,
  generateCustomerOrder,
  responseTimeForPatience,
} = require("../frontend/personas.js");

const expectedPersonas = [
  "executive",
  "sleep_deprived_student",
  "influencer",
  "coffee_snob",
  "indecisive_customer",
];
const canonicalOrder = {
  base: "espresso",
  milk: "oat milk",
  sweetness: "light sugar",
  topping: "boba",
  vibe: "cozy",
};

test("all required personas generate complete, valid request wording", () => {
  for (const personaId of expectedPersonas) {
    const generated = generateCustomerOrder(
      canonicalOrder,
      personaId,
      createSeededRandom(44),
    );
    assert.ok(generated.request.length > 20);
    assert.equal(generated.persona.id, personaId);
    assert.equal(generated.persona.display_name, PERSONAS[personaId].display_name);
    assert.match(generated.request, /espresso/i);
    assert.match(generated.request, /oat milk/i);
    assert.match(generated.request, /light sugar|not too sweet/i);
    assert.match(generated.request, /boba/i);
    assert.match(generated.request, /cozy/i);
  }
});

test("persona generation leaves canonical ground truth unchanged", () => {
  const original = structuredClone(canonicalOrder);
  generateCustomerOrder(canonicalOrder, "coffee_snob", createSeededRandom(7));
  assert.deepEqual(canonicalOrder, original);
});

test("difficulty variants change wording without modifying canonical recipe data", () => {
  for (const difficulty of ["easy", "normal", "ambiguous", "slang", "negation", "multi_clue"]) {
    const original = structuredClone(canonicalOrder);
    const generated = generateCustomerOrder(
      canonicalOrder,
      "sleep_deprived_student",
      createSeededRandom(88),
      difficulty,
      ["milk"],
    );
    assert.equal(generated.difficulty, difficulty);
    assert.ok(generated.request.length > 20);
    assert.match(generated.request, /oat milk/i);
    assert.deepEqual(canonicalOrder, original);
  }
});

test("repeatedly missed attributes keep clear canonical wording under harder variants", () => {
  const generated = generateCustomerOrder(
    canonicalOrder, "sleep_deprived_student", createSeededRandom(88), "ambiguous", ["milk"],
  );
  assert.match(generated.request, /oat milk/i);
  assert.doesNotMatch(generated.request, /plant-based milk/i);
});

test("seeded persona generation is reproducible", () => {
  const first = generateCustomerOrder(canonicalOrder, "indecisive_customer", createSeededRandom(123));
  const second = generateCustomerOrder(canonicalOrder, "indecisive_customer", createSeededRandom(123));
  assert.deepEqual(first, second);
});

test("persona patience changes the timer within fair bounds", () => {
  assert.equal(responseTimeForPatience(0.62), 28);
  assert.equal(responseTimeForPatience(1.12), 33);
  assert.ok(responseTimeForPatience(0) >= 27);
  assert.ok(responseTimeForPatience(2) <= 33);
});
