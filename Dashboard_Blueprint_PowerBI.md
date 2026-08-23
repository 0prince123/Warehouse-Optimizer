# Warehouse Optimization Dashboard — Power BI Blueprint

This guide covers three things: how to set up the data model, how to lay out
the dashboard pages, and the exact DAX measures to create. Follow it in order.

---

## 1. Data Model Setup

### Import these 7 files
In Power BI Desktop: **Home → Get Data → Text/CSV**, import each of:

| File | Role |
|---|---|
| `Products.csv` | Dimension table (product master) |
| `Sales_Transactions.csv` | Fact table (transactions) |
| `Inventory_Levels.csv` | Fact table (daily stock snapshots) |
| `Demand_Forecast_30d.csv` | Fact table (forecast) |
| `Safety_Stock_Recommendations.csv` | Fact table (1 row per product) |
| `Cost_Impact_Summary.csv` | Fact table (1 row per product) |
| `Warehouse_Transfer_Recommendations.csv` | Fact table (transfer suggestions) |

### Build the relationships
Go to **Model view** and connect everything back to `Products` as the hub
(star schema — this matters for DAX performance and correctness):

```
Products[product_id]  1 ──→ *  Sales_Transactions[product_id]
Products[product_id]  1 ──→ *  Inventory_Levels[product_id]
Products[product_id]  1 ──→ *  Demand_Forecast_30d[product_id]
Products[product_id]  1 ──→ 1  Safety_Stock_Recommendations[product_id]
Products[product_id]  1 ──→ 1  Cost_Impact_Summary[product_id]
Products[product_id]  1 ──→ *  Warehouse_Transfer_Recommendations[product_id]
```

All relationships: single direction, cardinality One-to-Many (or One-to-One
for the two summary tables), cross-filter direction "Single."

### Add a Date table (best practice — do this even though it feels optional)
**Modeling → New Table**:
```
DateTable = CALENDAR(MIN(Sales_Transactions[date]), MAX(Sales_Transactions[date]))
```
Mark it as a Date Table (Table tools → Mark as Date Table), then relate
`DateTable[Date]` to `Sales_Transactions[date]` and `Inventory_Levels[date]`.
This makes time-intelligence functions (YTD, MTD, etc.) actually work.

---

## 2. Page-by-Page Layout Plan

### Page 1 — Executive Overview
The page a manager glances at for 10 seconds and understands the business state.

- **Top row — 4 KPI cards** (from `KPI_Summary.csv`, or the measures below):
  `Total Revenue` | `Total Inventory Cost` | `Estimated Annual Savings` | `Products At Risk`
- **Left — line chart**: Daily revenue trend (last 90 days) with a forecast overlay for the next 30 days (use `Demand_Forecast_30d` × unit price)
- **Right — donut chart**: Revenue share by ABC Class (A/B/C)
- **Bottom — bar chart**: Revenue by Category

### Page 2 — Inventory Risk Monitor
The operational page someone checks every morning to decide what to reorder.

- **Table (the centerpiece)**: Product | Current Stock | Avg Daily Velocity | **Days of Safety Stock Remaining** | Lead Time | Risk Flag — conditional formatting: red if Days Remaining < Lead Time
- **KPI card**: Count of products flagged "AT RISK"
- **Bar chart**: Top 10 products by lowest days-of-stock-remaining
- **Slicer**: Category, Warehouse

### Page 3 — Cost Impact & ABC Analysis
The page that tells the "so what" story — good for a portfolio walkthrough.

- **KPI cards**: Naive Cost | Optimized Cost | Total Savings | % Reduction
- **Waterfall or clustered bar chart**: Naive vs Optimized cost, per product (top 10 by savings)
- **Table**: ABC Class, Product Count, Revenue Share % — with matrix visual
- **Scatter plot**: Safety Stock (x) vs Revenue (y), colored by ABC Class — shows which products deserve the most attention

### Page 4 — Warehouse Transfer Recommendations
- **Table**: Product | From Warehouse | To Warehouse | Qty | Reason
- **Card**: Count of active transfer recommendations
- (Optional, if you want to push further) a simple map or flow visual showing transfer volume between warehouse pairs

---

## 3. DAX Measures

Create these under **Modeling → New Measure**, on the `Products` table (keeps
them organized in one place regardless of which visual uses them).

### Core KPIs

```dax
Total Revenue =
SUM ( Sales_Transactions[revenue] )
```

```dax
Total Inventory Cost =
SUMX (
    -- most recent stock snapshot per product
    SUMMARIZE (
        FILTER (
            Inventory_Levels,
            Inventory_Levels[date] = CALCULATE ( MAX ( Inventory_Levels[date] ), ALLEXCEPT ( Inventory_Levels, Inventory_Levels[product_id] ) )
        ),
        Inventory_Levels[product_id],
        Inventory_Levels[stock_on_hand]
    ),
    VAR ProdCost = RELATED ( Products[unit_cost] )
    RETURN [stock_on_hand] * ProdCost
)
```

### Days of Safety Stock Remaining
This is the flagship metric from Step 4's request.

```dax
Avg Daily Velocity (30d) =
VAR MaxDate = MAX ( Sales_Transactions[date] )
RETURN
CALCULATE (
    AVERAGEX ( VALUES ( Sales_Transactions[date] ), CALCULATE ( SUM ( Sales_Transactions[units_sold] ) ) ),
    DATESINPERIOD ( Sales_Transactions[date], MaxDate, -30, DAY )
)
```

```dax
Current Stock =
VAR LatestDate =
    CALCULATE ( MAX ( Inventory_Levels[date] ), ALLEXCEPT ( Inventory_Levels, Inventory_Levels[product_id] ) )
RETURN
CALCULATE ( SUM ( Inventory_Levels[stock_on_hand] ), Inventory_Levels[date] = LatestDate )
```

```dax
Days of Safety Stock Remaining =
DIVIDE ( [Current Stock], [Avg Daily Velocity (30d)], BLANK() )
```

```dax
Stockout Risk Flag =
IF (
    [Days of Safety Stock Remaining] <= SELECTEDVALUE ( Products[lead_time_days] ),
    "AT RISK",
    "OK"
)
```

### ABC Classification (done in DAX, if you want it live rather than precomputed)

```dax
Product Revenue =
CALCULATE ( SUM ( Sales_Transactions[revenue] ) )
```

```dax
Cumulative Revenue % =
VAR CurrentProductRevenue = [Product Revenue]
VAR RunningTotal =
    SUMX (
        FILTER (
            ALL ( Products[product_id] ),
            CALCULATE ( [Product Revenue] ) >= CurrentProductRevenue
        ),
        CALCULATE ( [Product Revenue] )
    )
VAR GrandTotal = CALCULATE ( [Product Revenue], ALL ( Products ) )
RETURN
DIVIDE ( RunningTotal, GrandTotal )
```

```dax
ABC Class =
VAR Pct = [Cumulative Revenue %]
RETURN
SWITCH (
    TRUE(),
    Pct <= 0.80, "A",
    Pct <= 0.95, "B",
    "C"
)
```

*(Simpler alternative: since `02_analytical_queries.sql` already computes ABC
class in SQL, you can just import that query's output as an 8th table and
skip the DAX version above — less elegant to demo live, but faster and less
error-prone. Your call depending on how much you want to show off in DAX
specifically.)*

### Cost Impact (mostly pass-through from `Cost_Impact_Summary.csv`)

```dax
Total Naive Cost = SUM ( Cost_Impact_Summary[naive_annual_cost] )
Total Optimized Cost = SUM ( Cost_Impact_Summary[optimized_annual_cost] )
Total Estimated Savings = SUM ( Cost_Impact_Summary[estimated_savings] )

Pct Cost Reduction =
DIVIDE ( [Total Estimated Savings], [Total Naive Cost], BLANK() )
```

### Safety Stock Gap (shows how far off the old reorder points were)

```dax
Safety Stock Gap =
SUM ( Safety_Stock_Recommendations[recommended_reorder_point] )
    - SUM ( Safety_Stock_Recommendations[current_reorder_point] )
```

### Products At Risk (KPI card, Page 1 & 2)

```dax
Products At Risk =
CALCULATE (
    DISTINCTCOUNT ( Products[product_id] ),
    FILTER ( Products, [Stockout Risk Flag] = "AT RISK" )
)
```

---

## 4. A note on presenting this in an interview

When you walk someone through this dashboard, the strongest sequence is:
**Page 1 (the business impact)** → **Page 2 (how you catch problems day to
day)** → **Page 3 (the analytical rigor behind it)**. Leading with the dollar
figure and *then* showing the mechanism lands better than the reverse — most
interviewers care about impact first, method second.
