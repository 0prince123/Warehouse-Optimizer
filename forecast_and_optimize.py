"""
Warehouse Optimization Project
forecast_and_optimize.py

End-to-end pipeline that:
  1. Loads historical sales/inventory data
  2. Forecasts 30-day demand per product (Holt-Winters exponential smoothing)
  3. Calculates statistically-grounded safety stock & reorder points
     (95% service level: Z = 1.65)
  4. Quantifies the $ cost-impact of the optimized policy vs. a naive
     fixed-reorder-point baseline, via a day-by-day inventory simulation
  5. Produces an illustrative multi-warehouse transfer recommendation

All outputs are exported as clean CSVs ready to plug into Power BI / Tableau.

Requirements: pandas, numpy, statsmodels
    pip install pandas numpy statsmodels
"""

import warnings
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

warnings.filterwarnings("ignore")

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------
Z_SCORE_95 = 1.65          # service level constant for safety stock (~95%)
HOLDING_RATE_ANNUAL = 0.20 # cost of holding one unit in stock for a year, as % of unit cost
FORECAST_HORIZON_DAYS = 30
WAREHOUSES = ["WH-EAST", "WH-WEST", "WH-CENTRAL"]

# ------------------------------------------------------------------
# 1. LOAD DATA
# ------------------------------------------------------------------
sales = pd.read_csv("Sales_Transactions.csv", parse_dates=["date"])
products = pd.read_csv("Products.csv")
inventory = pd.read_csv("Inventory_Levels.csv", parse_dates=["date"])

daily_sales = (
    sales.groupby(["product_id", "date"])["units_sold"].sum().reset_index()
)

print(f"Loaded {len(products)} products, {len(sales)} transactions, "
      f"{daily_sales['date'].nunique()} days of history.\n")


# ------------------------------------------------------------------
# 2. DEMAND FORECASTING (Holt-Winters, 30-day horizon)
# ------------------------------------------------------------------
def get_daily_series(product_id: str) -> pd.Series:
    s = (
        daily_sales[daily_sales.product_id == product_id]
        .set_index("date")["units_sold"]
        .asfreq("D")
        .fillna(0)
    )
    return s


def forecast_product(product_id: str, horizon: int = FORECAST_HORIZON_DAYS):
    series = get_daily_series(product_id)
    model = ExponentialSmoothing(
        series, trend="add", seasonal="add", seasonal_periods=7, damped_trend=True
    )
    fit = model.fit(optimized=True)
    forecast = fit.forecast(horizon).clip(lower=0)
    resid_std = fit.resid.std()
    return forecast, resid_std


forecast_rows = []
demand_stats = []  # for safety stock calc

print("Forecasting demand for each product...")
for _, prod in products.iterrows():
    pid = prod.product_id
    series = get_daily_series(pid)
    forecast, resid_std = forecast_product(pid)

    last_date = series.index.max()
    for i, val in enumerate(forecast, start=1):
        forecast_rows.append({
            "product_id": pid,
            "date": (last_date + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
            "forecasted_units": round(max(val, 0), 2),
        })

    demand_stats.append({
        "product_id": pid,
        "avg_daily_demand": series.mean(),
        "stddev_daily_demand": series.std(),
        "forecast_resid_std": resid_std,
    })

forecast_df = pd.DataFrame(forecast_rows)
demand_stats_df = pd.DataFrame(demand_stats)
print(f"  Done. {forecast_df.shape[0]} forecasted product-days.\n")


# ------------------------------------------------------------------
# 3. SAFETY STOCK & RECOMMENDED REORDER POINT
# ------------------------------------------------------------------
opt = products.merge(demand_stats_df, on="product_id")
opt["safety_stock_95pct"] = (
    Z_SCORE_95 * opt["stddev_daily_demand"] * np.sqrt(opt["lead_time_days"])
).round(1)
opt["recommended_reorder_point"] = (
    opt["avg_daily_demand"] * opt["lead_time_days"] + opt["safety_stock_95pct"]
).round(1)
opt["current_reorder_point"] = opt["reorder_point"]

safety_stock_df = opt[[
    "product_id", "product_name", "lead_time_days", "avg_daily_demand",
    "stddev_daily_demand", "safety_stock_95pct", "recommended_reorder_point",
    "current_reorder_point"
]]

print("Safety stock & reorder points calculated for all products.\n")


# ------------------------------------------------------------------
# 4. COST-IMPACT SIMULATION: naive vs. optimized policy
# ------------------------------------------------------------------
def simulate_policy(demand, lead_time, reorder_point, order_qty, initial_stock):
    """Day-by-day simulation of an (s, Q) reorder policy.
    Returns total stockout units and cumulative unit-days held in stock
    (used to compute holding cost)."""
    stock = initial_stock
    pipeline = []  # list of (arrival_day, qty)
    stockout_units = 0
    holding_unit_days = 0.0

    for day in range(len(demand)):
        arrived = sum(q for (a, q) in pipeline if a == day)
        if arrived:
            stock += arrived
            pipeline = [(a, q) for (a, q) in pipeline if a != day]

        d = demand[day]
        if d <= stock:
            stock -= d
        else:
            stockout_units += (d - stock)
            stock = 0

        holding_unit_days += stock

        pipeline_qty = sum(q for (_, q) in pipeline)
        if stock + pipeline_qty <= reorder_point:
            pipeline.append((day + lead_time, order_qty))

    return stockout_units, holding_unit_days


cost_rows = []
holding_rate_daily = HOLDING_RATE_ANNUAL / 365

for _, row in opt.iterrows():
    pid = row.product_id
    demand = get_daily_series(pid).values
    lead_time = int(row.lead_time_days)

    # --- naive baseline: uses the arbitrary reorder_point already in Products.csv ---
    naive_qty = int(row.current_reorder_point * 3)
    so_naive, hold_naive = simulate_policy(
        demand, lead_time, row.current_reorder_point, naive_qty, naive_qty
    )

    # --- optimized: statistically-grounded reorder point & order-up-to qty ---
    opt_rp = int(round(row.recommended_reorder_point))
    opt_qty = max(opt_rp, 1)
    so_opt, hold_opt = simulate_policy(
        demand, lead_time, opt_rp, opt_qty, opt_qty
    )

    margin = row.unit_price - row.unit_cost
    naive_cost = so_naive * margin + hold_naive * row.unit_cost * holding_rate_daily
    opt_cost = so_opt * margin + hold_opt * row.unit_cost * holding_rate_daily

    cost_rows.append({
        "product_id": pid,
        "product_name": row.product_name,
        "naive_stockout_units": so_naive,
        "optimized_stockout_units": so_opt,
        "naive_annual_cost": round(naive_cost, 2),
        "optimized_annual_cost": round(opt_cost, 2),
        "estimated_savings": round(naive_cost - opt_cost, 2),
    })

cost_df = pd.DataFrame(cost_rows)
total_naive = cost_df.naive_annual_cost.sum()
total_opt = cost_df.optimized_annual_cost.sum()
total_savings = total_naive - total_opt

print("Cost-impact simulation complete:")
print(f"  Naive policy total cost:     ${total_naive:,.2f}")
print(f"  Optimized policy total cost: ${total_opt:,.2f}")
print(f"  Estimated annual savings:    ${total_savings:,.2f} "
      f"({100*total_savings/total_naive:.1f}% reduction)\n")

# NOTE ON INTERPRETATION:
# In this synthetic dataset, the "naive" reorder points were assigned
# randomly and are NOT correlated with actual product demand -- so the
# naive policy stocks out badly for fast-moving items. This is a realistic
# failure mode (arbitrary/ungrounded reorder points are a common real-world
# problem), but the magnitude of savings here is larger than typical
# published industry benchmarks (which usually cite ~10-30% cost reduction
# from improved safety-stock policies). Frame this project's finding as
# "demonstrates the mechanism and its direction," not a literal claim of
# 90%+ real-world savings.


# ------------------------------------------------------------------
# 5. MULTI-WAREHOUSE TRANSFER RECOMMENDATIONS (illustrative extension)
# ------------------------------------------------------------------
# The source data assigns each product to a single primary warehouse, so to
# demonstrate transfer logic we simulate a plausible regional demand split
# using a deterministic per-product random seed (stable across runs).
transfer_rows = []
latest_stock = (
    inventory.sort_values("date").groupby("product_id").tail(1)
    .set_index("product_id")["stock_on_hand"]
)

for _, row in opt.iterrows():
    pid = row.product_id
    rng = np.random.default_rng(abs(hash(pid)) % (2**32))
    demand_share = rng.dirichlet(np.ones(3))  # split across 3 warehouses
    stock_share = rng.dirichlet(np.ones(3))   # current stock isn't evenly matched to demand

    total_stock = latest_stock.get(pid, 0)
    daily_demand_total = row.avg_daily_demand

    wh_data = []
    for wh, d_share, s_share in zip(WAREHOUSES, demand_share, stock_share):
        wh_demand = daily_demand_total * d_share
        wh_stock = total_stock * s_share
        days_cover = wh_stock / wh_demand if wh_demand > 0 else np.inf
        wh_data.append({"warehouse": wh, "stock": wh_stock, "daily_demand": wh_demand,
                         "days_cover": days_cover})

    wh_df = pd.DataFrame(wh_data)
    surplus = wh_df.loc[wh_df.days_cover.idxmax()]
    shortfall = wh_df.loc[wh_df.days_cover.idxmin()]

    if shortfall.days_cover < row.lead_time_days and surplus.days_cover > row.lead_time_days * 2:
        transfer_qty = round(min(
            (surplus.days_cover - row.lead_time_days) * surplus.daily_demand * 0.5,
            surplus.stock * 0.3
        ), 0)
        if transfer_qty > 0:
            transfer_rows.append({
                "product_id": pid,
                "product_name": row.product_name,
                "from_warehouse": surplus.warehouse,
                "to_warehouse": shortfall.warehouse,
                "recommended_transfer_qty": int(transfer_qty),
                "reason": f"{shortfall.warehouse} has {shortfall.days_cover:.1f} days cover "
                          f"(< lead time {row.lead_time_days}d); "
                          f"{surplus.warehouse} has {surplus.days_cover:.1f} days cover"
            })

transfer_df = pd.DataFrame(transfer_rows)
print(f"Multi-warehouse transfer recommendations: {len(transfer_df)} suggested transfers.\n")


# ------------------------------------------------------------------
# 6. EXPORT ALL RESULTS
# ------------------------------------------------------------------
forecast_df.to_csv("Demand_Forecast_30d.csv", index=False)
safety_stock_df.to_csv("Safety_Stock_Recommendations.csv", index=False)
cost_df.to_csv("Cost_Impact_Summary.csv", index=False)
transfer_df.to_csv("Warehouse_Transfer_Recommendations.csv", index=False)

# a single summary row for the dashboard headline KPI card
summary = pd.DataFrame([{
    "total_naive_annual_cost": round(total_naive, 2),
    "total_optimized_annual_cost": round(total_opt, 2),
    "total_estimated_savings": round(total_savings, 2),
    "pct_cost_reduction": round(100 * total_savings / total_naive, 1),
    "products_flagged_at_risk": int((cost_df.optimized_stockout_units > 0).sum()),
    "transfer_recommendations_count": len(transfer_df),
}])
summary.to_csv("KPI_Summary.csv", index=False)

print("Exported: Demand_Forecast_30d.csv, Safety_Stock_Recommendations.csv, "
      "Cost_Impact_Summary.csv, Warehouse_Transfer_Recommendations.csv, KPI_Summary.csv")
