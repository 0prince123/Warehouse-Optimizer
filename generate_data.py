"""
Synthetic Warehouse Dataset Generator
--------------------------------------
Generates three linked CSV tables for a retail warehouse optimization project:
  1. Products.csv          - product catalog (master data)
  2. Inventory_Levels.csv  - daily stock snapshots per product/warehouse
  3. Sales_Transactions.csv- individual sales transactions over time

All tables link via `product_id`. Dates span the last 12 months so there's
enough history for time-series forecasting (Prophet/statsmodels) later.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

np.random.seed(42)

# ----------------------------
# 1. PRODUCTS (master table)
# ----------------------------
categories = {
    "Electronics": ["Wireless Mouse", "USB-C Cable", "Bluetooth Speaker", "Phone Charger",
                     "HDMI Cable", "Laptop Stand", "Webcam", "Power Bank"],
    "Home & Kitchen": ["Coffee Mug", "Non-Stick Pan", "Cutting Board", "Blender",
                       "Toaster", "Storage Containers", "Dish Rack", "Kettle"],
    "Apparel": ["Cotton T-Shirt", "Running Shoes", "Denim Jacket", "Wool Socks",
                "Baseball Cap", "Rain Jacket", "Yoga Pants", "Winter Gloves"],
    "Office Supplies": ["Notebook", "Ballpoint Pens (Pack)", "Desk Organizer", "Stapler",
                        "Sticky Notes", "Whiteboard Marker", "File Folder", "Desk Lamp"],
    "Sports & Outdoors": ["Yoga Mat", "Water Bottle", "Resistance Bands", "Camping Tent",
                          "Hiking Backpack", "Dumbbell Set", "Bicycle Helmet", "Tennis Racket"],
}

suppliers = ["Global Supply Co", "NorthStar Distributors", "PrimeSource Ltd",
             "Apex Wholesale", "BlueRiver Logistics", "Summit Trading Group"]

warehouses = ["WH-EAST", "WH-WEST", "WH-CENTRAL"]

rows = []
pid = 1000
for category, items in categories.items():
    for item in items:
        rows.append({
            "product_id": f"P{pid}",
            "product_name": item,
            "category": category,
            "unit_cost": round(np.random.uniform(3, 80), 2),
            "unit_price": None,  # filled below with markup
            "supplier": np.random.choice(suppliers),
            "reorder_point": np.random.randint(15, 60),
            "lead_time_days": np.random.randint(3, 21),
            "primary_warehouse": np.random.choice(warehouses),
        })
        pid += 1

products = pd.DataFrame(rows)
markup = np.random.uniform(1.3, 2.2, size=len(products))
products["unit_price"] = (products["unit_cost"] * markup).round(2)
products = products[[
    "product_id", "product_name", "category", "unit_cost", "unit_price",
    "supplier", "reorder_point", "lead_time_days", "primary_warehouse"
]]

# ----------------------------
# 2. SALES_TRANSACTIONS
# ----------------------------
start_date = datetime(2025, 8, 15)
end_date = datetime(2026, 8, 13)
date_range = pd.date_range(start_date, end_date, freq="D")

# give each product a baseline daily demand + seasonality + noise
sales_rows = []
txn_id = 500000

for _, prod in products.iterrows():
    base_demand = np.random.uniform(0.5, 8)  # avg units/day
    # some products trend up, some down, some flat
    trend = np.random.choice([-1, 0, 1], p=[0.25, 0.5, 0.25]) * np.random.uniform(0.0005, 0.003)
    weekend_boost = np.random.uniform(1.0, 1.6)

    for i, day in enumerate(date_range):
        seasonal = 1 + 0.3 * np.sin(2 * np.pi * i / 365)  # yearly seasonality
        dow_factor = weekend_boost if day.weekday() >= 5 else 1.0
        trend_factor = max(0.1, 1 + trend * i)
        lam = max(0.01, base_demand * seasonal * dow_factor * trend_factor)
        units_sold = np.random.poisson(lam)

        if units_sold > 0:
            txn_id += 1
            sales_rows.append({
                "transaction_id": f"T{txn_id}",
                "date": day.strftime("%Y-%m-%d"),
                "product_id": prod["product_id"],
                "units_sold": int(units_sold),
                "unit_price": prod["unit_price"],
                "revenue": round(units_sold * prod["unit_price"], 2),
                "warehouse": prod["primary_warehouse"],
                "channel": np.random.choice(["Online", "In-Store"], p=[0.65, 0.35]),
            })

sales = pd.DataFrame(sales_rows)

# ----------------------------
# 3. INVENTORY_LEVELS (daily snapshot per product)
# ----------------------------
inv_rows = []
daily_sales = sales.groupby(["product_id", "date"])["units_sold"].sum().reset_index()
daily_sales_pivot = daily_sales.pivot(index="date", columns="product_id", values="units_sold").fillna(0)
daily_sales_pivot = daily_sales_pivot.reindex(date_range.strftime("%Y-%m-%d")).fillna(0)

for _, prod in products.iterrows():
    pid_ = prod["product_id"]
    stock = np.random.randint(prod["reorder_point"] * 2, prod["reorder_point"] * 5)
    restock_qty = int(prod["reorder_point"] * np.random.uniform(2.5, 4))

    for day_str in date_range.strftime("%Y-%m-%d"):
        sold_today = int(daily_sales_pivot.loc[day_str, pid_]) if pid_ in daily_sales_pivot.columns else 0
        stock -= sold_today

        restocked = 0
        if stock <= prod["reorder_point"]:
            restocked = restock_qty
            stock += restocked

        stock = max(stock, 0)

        inv_rows.append({
            "date": day_str,
            "product_id": pid_,
            "warehouse": prod["primary_warehouse"],
            "stock_on_hand": int(stock),
            "units_sold": sold_today,
            "restocked_units": restocked,
            "reorder_point": prod["reorder_point"],
        })

inventory = pd.DataFrame(inv_rows)

# ----------------------------
# EXPORT
# ----------------------------
products.to_csv("Products.csv", index=False)
sales.to_csv("Sales_Transactions.csv", index=False)
inventory.to_csv("Inventory_Levels.csv", index=False)

print("Products:", products.shape)
print("Sales_Transactions:", sales.shape)
print("Inventory_Levels:", inventory.shape)
print("\nSample Products:\n", products.head(3).to_string())
print("\nSample Sales:\n", sales.head(3).to_string())
print("\nSample Inventory:\n", inventory.head(3).to_string())
