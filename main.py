from fastapi import FastAPI
import requests
import pandas as pd
import numpy as np
import datetime

app = FastAPI()

# ==============================
# FETCH DATA
# ==============================
def get_binance_data(interval="5m"):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": "BTCUSDT", "interval": interval, "limit": 100}
    data = requests.get(url, params=params).json()

    df = pd.DataFrame(data, columns=[
        "time","open","high","low","close","volume",
        "close_time","qav","trades","tbbav","tbqav","ignore"
    ])

    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)

    return df


# ==============================
# TREND
# ==============================
def get_trend(df):
    if df["close"].iloc[-2] > df["close"].iloc[-6]:
        return "UP"
    else:
        return "DOWN"


# ==============================
# LIQUIDITY
# ==============================
def detect_liquidity(df):
    highs = df["high"].tail(10).values
    lows = df["low"].tail(10).values

    liquidity_above = np.std(highs) < 10
    liquidity_below = np.std(lows) < 10

    return liquidity_above, liquidity_below


# ==============================
# ANALYSIS
# ==============================
def analyze_market(df, trend):
    price = df["close"].iloc[-2]
    support = df["low"].rolling(20).min().iloc[-2]
    resistance = df["high"].rolling(20).max().iloc[-2]

    rr1, rr2, rr3 = 1, 2, 3
    confidence = 0
    reason = []

    avg_volume = df["volume"].rolling(10).mean().iloc[-2]
    current_volume = df["volume"].iloc[-2]

    if current_volume > avg_volume:
        confidence += 20
        reason.append("Volume spike")

    liquidity_above, liquidity_below = detect_liquidity(df)

    if trend == "UP" and price > support:
        signal = "BUY"
        sl = support
        risk = price - sl

        entry_low = support
        entry_high = support + (risk * 0.3)

        tp1 = price + (risk * rr1)
        tp2 = price + (risk * rr2)
        tp3 = price + (risk * rr3)

        confidence += 30
        reason.append("Uptrend + support")

        if liquidity_below:
            confidence += 20
            reason.append("Liquidity below")

    elif trend == "DOWN" and price < resistance:
        signal = "SELL"
        sl = resistance + 10
        risk = sl - price

        entry_low = resistance - (risk * 0.3)
        entry_high = resistance

        tp1 = price - (risk * rr1)
        tp2 = price - (risk * rr2)
        tp3 = price - (risk * rr3)

        confidence += 30
        reason.append("Downtrend + resistance")

        if liquidity_above:
            confidence += 20
            reason.append("Liquidity above")

    else:
        signal = "WAIT"
        sl = price
        entry_low = price
        entry_high = price
        tp1 = price
        tp2 = price
        tp3 = price
        reason.append("No setup")

    if price < entry_low:
        status = "WAIT"
    elif entry_low <= price <= entry_high:
        status = "ENTER NOW"
    else:
        status = "MISSED"

    signal_time = datetime.datetime.now().strftime("%H:%M:%S")

    if confidence >= 70:
        strength = "STRONG"
    elif confidence >= 50:
        strength = "MEDIUM"
    else:
        strength = "WEAK"

    return {
        "signal": signal,
        "strength": strength,
        "entry_zone": [float(round(entry_low,2)), float(round(entry_high,2))],
        "sl": float(round(sl,2)),
        "tp1": float(round(tp1,2)),
        "tp2": float(round(tp2,2)),
        "tp3": float(round(tp3,2)),
        "confidence": confidence,
        "trend": trend,
        "status": status,
        "signal_time": signal_time,
        "reason": " | ".join(reason)
    }


# ==============================
# API ROUTE
# ==============================
@app.get("/analyze")
def analyze():
    df_5m = get_binance_data("5m")
    df_15m = get_binance_data("15m")

    trend_5m = get_trend(df_5m)
    trend_15m = get_trend(df_15m)

    if trend_5m != trend_15m:
        return {"signal": "WAIT", "reason": "Timeframes not aligned"}

    return analyze_market(df_5m, trend_5m)
