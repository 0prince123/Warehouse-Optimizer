-- ============================================================
-- Warehouse Optimization Project
-- 01_schema_and_import.sql
-- Creates the database schema and loads the three source CSVs.
-- Target: PostgreSQL 13+
-- ============================================================

-- Run this once to create a dedicated database, then connect to it
-- before running the rest of this script:
--   createdb warehouse_optimization
--   psql -d warehouse_optimization -f 01_schema_and_import.sql

DROP TABLE IF EXISTS sales_transactions CASCADE;
DROP TABLE IF EXISTS inventory_levels CASCADE;
DROP TABLE IF EXISTS products CASCADE;

-- ------------------------------------------------------------
-- Master table: one row per product (SKU)
-- ------------------------------------------------------------
CREATE TABLE products (
    product_id          VARCHAR(10)     PRIMARY KEY,
    product_name        VARCHAR(100)    NOT NULL,
    category            VARCHAR(50)     NOT NULL,
    unit_cost           NUMERIC(10,2)   NOT NULL,
    unit_price          NUMERIC(10,2)   NOT NULL,
    supplier            VARCHAR(100),
    reorder_point       INTEGER         NOT NULL,   -- naive baseline; we calculate a better one in 02_analytical_queries.sql
    lead_time_days      INTEGER         NOT NULL,
    primary_warehouse   VARCHAR(20)     NOT NULL
);

-- ------------------------------------------------------------
-- Transactional table: one row per sale
-- ------------------------------------------------------------
CREATE TABLE sales_transactions (
    transaction_id  VARCHAR(15)     PRIMARY KEY,
    date            DATE            NOT NULL,
    product_id      VARCHAR(10)     NOT NULL REFERENCES products(product_id),
    units_sold      INTEGER         NOT NULL,
    unit_price      NUMERIC(10,2)   NOT NULL,
    revenue         NUMERIC(10,2)   NOT NULL,
    warehouse       VARCHAR(20)     NOT NULL,
    channel         VARCHAR(20)     NOT NULL
);

-- ------------------------------------------------------------
-- Daily snapshot table: one row per product per day
-- ------------------------------------------------------------
CREATE TABLE inventory_levels (
    date                DATE            NOT NULL,
    product_id          VARCHAR(10)     NOT NULL REFERENCES products(product_id),
    warehouse           VARCHAR(20)     NOT NULL,
    stock_on_hand       INTEGER         NOT NULL,
    units_sold          INTEGER         NOT NULL,
    restocked_units     INTEGER         NOT NULL,
    reorder_point       INTEGER         NOT NULL,
    PRIMARY KEY (date, product_id)
);

-- Indexes to speed up the analytical queries in the next file
CREATE INDEX idx_sales_product_date ON sales_transactions (product_id, date);
CREATE INDEX idx_inventory_product_date ON inventory_levels (product_id, date);

-- ------------------------------------------------------------
-- Import the CSVs
-- NOTE: adjust the file paths below to wherever you saved the CSVs.
-- \copy runs client-side (works from psql without server file access);
-- use COPY (server-side) instead if running on a remote Postgres server.
-- ------------------------------------------------------------
\copy products FROM 'Products.csv' WITH (FORMAT csv, HEADER true);
\copy sales_transactions FROM 'Sales_Transactions.csv' WITH (FORMAT csv, HEADER true);
\copy inventory_levels FROM 'Inventory_Levels.csv' WITH (FORMAT csv, HEADER true);

-- Quick sanity check
SELECT 'products' AS table_name, COUNT(*) FROM products
UNION ALL
SELECT 'sales_transactions', COUNT(*) FROM sales_transactions
UNION ALL
SELECT 'inventory_levels', COUNT(*) FROM inventory_levels;
