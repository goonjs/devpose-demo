const API_URL = process.env.DEMO_API_URL || "http://localhost:3000";

function greet(name) {
  if (!name || !name.trim()) return "Hello!";
  return `Hello, ${name.trim()}!`;
}

function farewell(name) {
  return `Goodbye, ${name.trim()}!`;
}

module.exports = { greet, farewell, API_URL };
