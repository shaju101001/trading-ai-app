from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
import pandas as pd
import numpy as np
from datetime import datetime

app = FastAPI()

# ✅ CORS FIX (VERY IMPORTANT)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔥 GET DATA FROM BINANCE
def get_binance_data(interval="5m", limit=100):
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": "BTCUSDT",
        "interval": interval,
        "limit": limit
    }
    data = requests.get(url, params=params).json()

    df = pd.DataFrame(data, columns=[
        "time","open","high","low","close","volume",
        "close_time","qav","trades","tbbav","tbqav","ignore"
    ])

    df["close"] = df["close"].astype(float)
    return df

# 🔥 ANALYSIS LOGIC
def analyze_market():
    df_15m = get_binance_data("15m")
    df_1h = get_binance_data("1h")

    current_price = df_15m["close"].iloc[-1]

    # EMA
    df_15m["ema20"] = df_15m["close"].ewm(span=20).mean()
    df_1h["ema20"] = df_1h["close"].ewm(span=20).mean()

    # TREND
    trend_15m = "UP" if df_15m["close"].iloc[-1] > df_15m["ema20"].iloc[-1] else "DOWN"
    trend_1h = "UP" if df_1h["close"].iloc[-1] > df_1h["ema20"].iloc[-1] else "DOWN"

    # 🔥 LOGIC (NO WAIT — ALWAYS ACTION)
    if trend_1h == "DOWN":
        action = "SELL NOW"
        entry = current_price
        target = current_price - 300
        sl = current_price + 150
        reason = "Strong downtrend, selling pressure"
        market_trend = "DOWN"

    elif trend_1h == "UP":
        action = "BUY NOW"
        entry = current_price
        target = current_price + 300
        sl = current_price - 150
        reason = "Strong uptrend, buying pressure"
        market_trend = "UP"

    else:
        action = "WAIT"
        entry = current_price
        target = current_price
        sl = current_price
        reason = "No clear trend"
        market_trend = "SIDEWAYS"

    return {
        "market_trend": market_trend,
        "current_phase": "LIVE MARKET",
        "action_now": action,
        "entry": round(entry, 2),
        "primary_target": round(target, 2),
        "sl": round(sl, 2),
        "reason": reason,
        "trend_1h": trend_1h,
        "trend_15m": trend_15m,
        "time": datetime.now().strftime("%H:%M:%S")
    }

# 🚀 API ROUTE
@app.get("/analyze")
def analyze():
    return analyze_market()
