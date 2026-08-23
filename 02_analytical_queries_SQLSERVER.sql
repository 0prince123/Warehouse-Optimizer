-- ============================================================
-- Warehouse Optimization Project
-- 02_analytical_queries_SQLSERVER.sql
-- Same three analytical queries as the PostgreSQL version, adapted
-- to T-SQL syntax for SQL Server / SSMS. Logic is identical --
-- only syntax differences below (noted inline).
-- ============================================================

USE WarehouseOptimization;
GO

-- ============================================================
-- QUERY 1: ABC (Pareto) Product Classification
-- ============================================================
WITH product_revenue AS (
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        SUM(s.revenue) AS total_revenue
    FROM products p
    JOIN sales_transactions s ON p.product_id = s.product_id
    GROUP BY p.product_id, p.product_name, p.category
),
ranked AS (
    SELECT
        *,
        SUM(total_revenue) OVER (ORDER BY total_revenue DESC
                                  ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_revenue,
        SUM(total_revenue) OVER () AS grand_total_revenue,
        ROW_NUMBER() OVER (ORDER BY total_revenue DESC) AS revenue_rank
    FROM product_revenue
)
SELECT
    product_id,
    product_name,
    category,
    total_revenue,
    ROUND(100.0 * running_revenue / grand_total_revenue, 2) AS cumulative_pct,
    CASE
        WHEN running_revenue / grand_total_revenue <= 0.80 THEN 'A'
        WHEN running_revenue / grand_total_revenue <= 0.95 THEN 'B'
        ELSE 'C'
    END AS abc_class
FROM ranked
ORDER BY revenue_rank;
GO


-- ============================================================
-- QUERY 2: Sales Velocity & Days-to-Stockout
-- T-SQL difference: DATEADD(DAY, -30, ...) instead of INTERVAL '30 days'
-- ============================================================
WITH daily_sales AS (
    SELECT product_id, [date], SUM(units_sold) AS units_sold
    FROM sales_transactions
    GROUP BY product_id, [date]
),
recent_velocity AS (
    SELECT
        product_id,
        AVG(CAST(units_sold AS FLOAT)) AS avg_daily_velocity_30d,
        STDEV(units_sold) AS stddev_daily_velocity_30d   -- STDEV = sample stddev in T-SQL (equivalent to Postgres STDDEV_SAMP)
    FROM daily_sales
    WHERE [date] >= DATEADD(DAY, -30, (SELECT MAX([date]) FROM daily_sales))
    GROUP BY product_id
),
latest_stock AS (
    SELECT
        product_id,
        stock_on_hand,
        ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY [date] DESC) AS rn
    FROM inventory_levels
)
SELECT
    p.product_id,
    p.product_name,
    ls.stock_on_hand AS current_stock,
    ROUND(rv.avg_daily_velocity_30d, 2) AS avg_daily_velocity,
    ROUND(ls.stock_on_hand / NULLIF(rv.avg_daily_velocity_30d, 0), 1) AS days_of_stock_remaining,
    p.lead_time_days,
    CASE
        WHEN ls.stock_on_hand / NULLIF(rv.avg_daily_velocity_30d, 0) <= p.lead_time_days
        THEN 'AT RISK - reorder now'
        ELSE 'OK'
    END AS stockout_risk_flag
FROM products p
JOIN recent_velocity rv ON p.product_id = rv.product_id
JOIN latest_stock ls ON p.product_id = ls.product_id AND ls.rn = 1
ORDER BY days_of_stock_remaining ASC;
GO


-- ============================================================
-- QUERY 3: Statistical Safety Stock & Recommended Reorder Point
-- Same formula as before: Safety Stock = Z * stddev(daily demand) * sqrt(lead time)
-- ============================================================
WITH daily_sales AS (
    SELECT product_id, [date], SUM(units_sold) AS units_sold
    FROM sales_transactions
    GROUP BY product_id, [date]
),
demand_stats AS (
    SELECT
        product_id,
        AVG(CAST(units_sold AS FLOAT)) AS avg_daily_demand,
        STDEV(units_sold) AS stddev_daily_demand
    FROM daily_sales
    GROUP BY product_id
)
SELECT
    p.product_id,
    p.product_name,
    p.lead_time_days,
    ROUND(ds.avg_daily_demand, 2) AS avg_daily_demand,
    ROUND(ds.stddev_daily_demand, 2) AS demand_stddev,
    ROUND(1.65 * ds.stddev_daily_demand * SQRT(p.lead_time_days), 1) AS safety_stock_95pct,
    ROUND((ds.avg_daily_demand * p.lead_time_days)
          + (1.65 * ds.stddev_daily_demand * SQRT(p.lead_time_days)), 1) AS recommended_reorder_point,
    p.reorder_point AS current_reorder_point
FROM products p
JOIN demand_stats ds ON p.product_id = ds.product_id
ORDER BY p.product_id;
GO
