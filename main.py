
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import numpy as np
import pandas as pd
import smtplib
from email.message import EmailMessage

app = FastAPI()

# CORS 設定（允許 Power BI 訪問）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Email 通知函數
def send_email_alert(item_id, inventory, rop, eoq):
    msg = EmailMessage()
    msg['Subject'] = f"[JIT 庫存警示] {item_id} 低於補貨點！"
    msg['From'] = "your_email@gmail.com"
    msg['To'] = "recipient@example.com"  # 改為實際收件人
    msg.set_content(
        f"警告：{item_id} 的庫存已降至 {inventory}（ROP = {rop})\n"
        f"建議立即補貨 EOQ = {eoq} 單位"
    )
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login("your_email@gmail.com", "your_app_password")
            smtp.send_message(msg)
    except Exception as e:
        print("Email 發送失敗：", e)

# 模擬資料（30天）
days = 30
np.random.seed(42)
demand = np.random.poisson(lam=20, size=days)
alpha = 0.3
z = 1.645
lead_time = 3
order_cost = 50
holding_cost = 2.0
initial_inventory = 100

forecast = [demand[0]]
for t in range(1, days):
    forecast.append(alpha * demand[t - 1] + (1 - alpha) * forecast[t - 1])

demand_std = np.std(demand[:10])
safety_stock = z * demand_std * np.sqrt(lead_time)
rop = np.array(forecast) * lead_time + safety_stock
total_annual_demand = np.sum(demand) * (365 / days)
eoq = int(np.sqrt((2 * total_annual_demand * order_cost) / (holding_cost * 365)))

inventory = [initial_inventory]
orders = [0]
pending_orders = []

for t in range(1, days):
    arrivals = sum(q for day, q in pending_orders if day == t)
    pending_orders = [(day, q) for day, q in pending_orders if day != t]
    current_inventory = inventory[-1] + arrivals - demand[t]
    current_inventory = max(current_inventory, 0)

    if current_inventory <= rop[t]:
        orders.append(eoq)
        pending_orders.append((t + lead_time, eoq))
    else:
        orders.append(0)

    inventory.append(current_inventory)

df = pd.DataFrame({
    "day": list(range(days)),
    "demand": demand,
    "forecast": np.round(forecast, 2),
    "ROP": np.round(rop, 2),
    "inventory": inventory,
    "order": orders
})

@app.get("/api/inventory-status")
def get_inventory_status():
    records = df.tail(1).to_dict(orient="records")[0]
    if records["inventory"] <= records["ROP"]:
        send_email_alert("gloves_001", records["inventory"], records["ROP"], eoq)
    return {
        "item_id": "gloves_001",
        "inventory": records["inventory"],
        "forecast_demand": records["forecast"],
        "ROP": records["ROP"],
        "safety_stock": round(safety_stock, 2),
        "recommended_order": eoq
    }

@app.get("/api/kpi-metrics")
def get_kpi_metrics():
    avg_inventory = np.mean(inventory)
    turnover_rate = int(np.sum(demand) / avg_inventory)
    total_cost = ((np.sum(demand) / eoq) * order_cost) + ((eoq / 2) * holding_cost)
    return {
        "EOQ": eoq,
        "total_cost": round(total_cost, 2),
        "turnover_rate": round(turnover_rate, 2),
        "stockout_risk": round(1.0 / (1.0 + safety_stock), 4)
    }

@app.get("/api/daily-demand")
def get_daily_demand():
    return df.to_dict(orient="records")
