const test = require("node:test");
const assert = require("node:assert");
const { greet, farewell } = require("../src/app");

test("greet says hello", () => {
  assert.strictEqual(greet("Acme"), "Hello, Acme!");
});

test("greet trims the name", () => {
  assert.strictEqual(greet("  Acme "), "Hello, Acme!");
});

test("farewell says goodbye", () => {
  assert.strictEqual(farewell("Acme"), "Goodbye, Acme!");
});
