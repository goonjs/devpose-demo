-- Demo migration: adds an orders table (backward compatible: new table only).
CREATE TABLE orders (
  id SERIAL PRIMARY KEY,
  customer TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
