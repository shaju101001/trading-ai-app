from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import pandas as pd
import numpy as np
from datetime import datetime

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BINANCE_URL = "https://api.binance.com/api/v3/klines"

# =========================
# DATA FETCH (ASYNC)
# =========================
async def get_binance_data(interval="5m", limit=150):
    params = {
        "symbol": "BTCUSDT",
        "interval": interval,
        "limit": limit
    }

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(BINANCE_URL, params=params)
        r.raise_for_status()
        data = r.json()

    df = pd.DataFrame(data, columns=[
        "time","open","high","low","close","volume",
        "close_time","qav","trades","tbbav","tbqav","ignore"
    ])

    for col in ["open","high","low","close","volume"]:
        df[col] = df[col].astype(float)

    return df

# =========================
# INDICATORS
# =========================
def add_indicators(df):
    # EMA
    df["ema20"] = df["close"].ewm(span=20).mean()
    df["ema50"] = df["close"].ewm(span=50).mean()

    # RSI
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))

    # ATR
    df["tr"] = np.maximum(df["high"] - df["low"],
                           np.maximum(abs(df["high"] - df["close"].shift()),
                                      abs(df["low"] - df["close"].shift())))
    df["atr"] = df["tr"].rolling(14).mean()

    return df

# =========================
# SUPPORT / RESISTANCE
# =========================
def get_levels(df):
    recent = df.tail(50)
    support = recent["low"].min()
    resistance = recent["high"].max()
    return support, resistance

# =========================
# AI-LIKE ANALYSIS ENGINE
# =========================
def generate_signal(df_15m, df_1h):
    price = df_15m["close"].iloc[-1]

    # Trend
    trend_1h = "UP" if df_1h["ema20"].iloc[-1] > df_1h["ema50"].iloc[-1] else "DOWN"
    trend_15m = "UP" if df_15m["ema20"].iloc[-1] > df_15m["ema50"].iloc[-1] else "DOWN"

    # Momentum
    rsi = df_15m["rsi"].iloc[-1]

    # Volatility
    atr = df_15m["atr"].iloc[-1]

    # Levels
    support, resistance = get_levels(df_15m)

    # =========================
    # DECISION ENGINE
    # =========================

    action = "WAIT"
    reason = []

    if trend_1h == "UP" and trend_15m == "UP" and rsi > 55:
        action = "BUY"
        reason.append("Multi-timeframe uptrend")
        reason.append("RSI bullish")

    elif trend_1h == "DOWN" and trend_15m == "DOWN" and rsi < 45:
        action = "SELL"
        reason.append("Multi-timeframe downtrend")
        reason.append("RSI bearish")

    else:
        reason.append("No strong confirmation")

    # Targets using ATR
    if action == "BUY":
        entry = price
        target = price + (2 * atr)
        sl = price - atr

    elif action == "SELL":
        entry = price
        target = price - (2 * atr)
        sl = price + atr

    else:
        entry = price
        target = price
        sl = price

    # Confidence Score (simple AI feel)
    confidence = 0
    if trend_1h == trend_15m:
        confidence += 40
    if (rsi > 55 and action == "BUY") or (rsi < 45 and action == "SELL"):
        confidence += 30
    if abs(price - support) > atr and abs(price - resistance) > atr:
        confidence += 30

    return {
        "action": action,
        "entry": round(entry, 2),
        "target": round(target, 2),
        "stoploss": round(sl, 2),
        "confidence": f"{confidence}%",
        "trend_1h": trend_1h,
        "trend_15m": trend_15m,
        "rsi": round(rsi, 2),
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "reason": reason
    }

# =========================
# API ROUTE
# =========================
@app.get("/analyze")
async def analyze():
    try:
        df_15m = await get_binance_data("15m")
        df_1h = await get_binance_data("1h")

        df_15m = add_indicators(df_15m)
        df_1h = add_indicators(df_1h)

        result = generate_signal(df_15m, df_1h)

        return {
            "time": datetime.now().strftime("%H:%M:%S"),
            "market_status": "LIVE",
            "signal": result
        }

    except Exception as e:
        return {"error": str(e)}
