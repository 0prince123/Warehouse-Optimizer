-- ============================================================
-- Warehouse Optimization Project
-- 01_schema_and_import_SQLSERVER.sql
-- Creates the database schema for SQL Server / SSMS.
-- CSV import is done via the SSMS Import Wizard (see instructions below)
-- rather than in this script, since that's far more beginner-friendly
-- than BULK INSERT file paths.
-- ============================================================

-- Step 1: Create the database (run this first, alone, then connect to it)
-- CREATE DATABASE WarehouseOptimization;
-- GO
-- Then in SSMS: right-click WarehouseOptimization in Object Explorer ->
-- "New Query" so the rest of this script runs against that database.

USE WarehouseOptimization;
GO

IF OBJECT_ID('sales_transactions', 'U') IS NOT NULL DROP TABLE sales_transactions;
IF OBJECT_ID('inventory_levels', 'U') IS NOT NULL DROP TABLE inventory_levels;
IF OBJECT_ID('products', 'U') IS NOT NULL DROP TABLE products;
GO

-- ------------------------------------------------------------
-- Master table: one row per product (SKU)
-- ------------------------------------------------------------
CREATE TABLE products (
    product_id          VARCHAR(10)     PRIMARY KEY,
    product_name        VARCHAR(100)    NOT NULL,
    category             VARCHAR(50)     NOT NULL,
    unit_cost            DECIMAL(10,2)   NOT NULL,
    unit_price           DECIMAL(10,2)   NOT NULL,
    supplier             VARCHAR(100),
    reorder_point        INT             NOT NULL,
    lead_time_days       INT             NOT NULL,
    primary_warehouse    VARCHAR(20)     NOT NULL
);
GO

-- ------------------------------------------------------------
-- Transactional table: one row per sale
-- ------------------------------------------------------------
CREATE TABLE sales_transactions (
    transaction_id  VARCHAR(15)     PRIMARY KEY,
    [date]          DATE            NOT NULL,   -- bracketed: DATE is a reserved word in T-SQL
    product_id      VARCHAR(10)     NOT NULL REFERENCES products(product_id),
    units_sold      INT             NOT NULL,
    unit_price      DECIMAL(10,2)   NOT NULL,
    revenue         DECIMAL(10,2)   NOT NULL,
    warehouse       VARCHAR(20)     NOT NULL,
    channel         VARCHAR(20)     NOT NULL
);
GO

-- ------------------------------------------------------------
-- Daily snapshot table: one row per product per day
-- ------------------------------------------------------------
CREATE TABLE inventory_levels (
    [date]              DATE            NOT NULL,
    product_id          VARCHAR(10)     NOT NULL REFERENCES products(product_id),
    warehouse           VARCHAR(20)     NOT NULL,
    stock_on_hand        INT             NOT NULL,
    units_sold           INT             NOT NULL,
    restocked_units       INT             NOT NULL,
    reorder_point         INT             NOT NULL,
    PRIMARY KEY ([date], product_id)
);
GO

CREATE INDEX idx_sales_product_date ON sales_transactions (product_id, [date]);
CREATE INDEX idx_inventory_product_date ON inventory_levels (product_id, [date]);
GO

-- ============================================================
-- HOW TO IMPORT THE CSVs (do this in the SSMS GUI, not this script)
-- ============================================================
-- 1. In Object Explorer, expand Databases -> WarehouseOptimization
-- 2. Right-click WarehouseOptimization -> Tasks -> Import Flat File...
-- 3. Point it at Products.csv
--    - Set the destination table name to: products
--    - On the "Modify Columns" screen, double-check data types match
--      the CREATE TABLE above (VARCHAR/DECIMAL/INT/DATE) — the wizard
--      sometimes guesses wrong (e.g. picks NVARCHAR(50) or FLOAT)
--    - IMPORTANT: since the `products` table already exists (created
--      above), the wizard will just insert into it if you select the
--      existing table name — don't let it auto-create a duplicate table
-- 4. Repeat for Sales_Transactions.csv -> sales_transactions
-- 5. Repeat for Inventory_Levels.csv -> inventory_levels
--    (import products first, then sales/inventory, since they have
--    foreign keys pointing back to products)

-- Quick sanity check after importing:
SELECT 'products' AS table_name, COUNT(*) AS row_count FROM products
UNION ALL
SELECT 'sales_transactions', COUNT(*) FROM sales_transactions
UNION ALL
SELECT 'inventory_levels', COUNT(*) FROM inventory_levels;
