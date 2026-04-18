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
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": "BTCUSDT", "interval": interval, "limit": 100}
        response = requests.get(url, params=params, timeout=10)

        if response.status_code != 200:
            return pd.DataFrame()

        data = response.json()

        if not isinstance(data, list):
            return pd.DataFrame()

        df = pd.DataFrame(data, columns=[
            "time","open","high","low","close","volume",
            "close_time","qav","trades","tbbav","tbqav","ignore"
        ])

        for col in ["open","high","low","close","volume"]:
            df[col] = df[col].astype(float)

        return df
    except:
        return pd.DataFrame()


# ==============================
# TREND
# ==============================
def get_trend(df):
    try:
        if df["close"].iloc[-2] > df["close"].iloc[-6]:
            return "UP"
        else:
            return "DOWN"
    except:
        return "SIDEWAYS"


# ==============================
# ANALYSIS
# ==============================
def analyze_market(df, trend):
    try:
        price = df["close"].iloc[-2]
        support = df["low"].rolling(20).min().iloc[-2]
        resistance = df["high"].rolling(20).max().iloc[-2]

        rr1, rr2, rr3 = 1, 2, 3
        confidence = 30  # base confidence
        reason = []

        # ==========================
        # SIGNAL
        # ==========================
        if trend == "UP":
            signal = "BUY"
            sl = support
            risk = max(price - sl, 1)

            pullback_low = support
            pullback_high = support + (risk * 0.3)

            tp1 = price + (risk * rr1)
            tp2 = price + (risk * rr2)
            tp3 = price + (risk * rr3)

        else:
            signal = "SELL"
            sl = resistance + 10
            risk = max(sl - price, 1)

            pullback_low = resistance - (risk * 0.3)
            pullback_high = resistance

            tp1 = price - (risk * rr1)
            tp2 = price - (risk * rr2)
            tp3 = price - (risk * rr3)

        # ==========================
        # SMART ENTRY SYSTEM (FINAL)
        # ==========================
        entry_type = "PULLBACK"
        entry_low = pullback_low
        entry_high = pullback_high

        # 🔥 1. CONTINUATION ENTRY (MOST IMPORTANT FIX)
        if trend == "DOWN" and price < pullback_low:
            entry_type = "CONTINUATION"
            entry_low = price
            entry_high = price
            reason.append("Downtrend continuation")

        elif trend == "UP" and price > pullback_high:
            entry_type = "CONTINUATION"
            entry_low = price
            entry_high = price
            reason.append("Uptrend continuation")

        # 🔥 2. MARKET ENTRY (IF TOO FAR)
        elif abs(price - pullback_high) > (risk * 1.5):
            entry_type = "MARKET"
            entry_low = price
            entry_high = price
            reason.append("Momentum entry")

        # 🔥 3. PULLBACK ENTRY
        else:
            reason.append("Pullback entry")

        # ==========================
        # STATUS
        # ==========================
        if entry_low <= price <= entry_high:
            status = "ENTER NOW"
        elif trend == "DOWN" and price < entry_low:
            status = "RUNNING"
        elif trend == "UP" and price > entry_high:
            status = "RUNNING"
        else:
            status = "WAIT"

        # ==========================
        # RR
        # ==========================
        if abs(entry_low - sl) > 0:
            rr = abs(tp1 - entry_low) / abs(entry_low - sl)
        else:
            rr = 0

        signal_time = datetime.datetime.now().strftime("%H:%M:%S")

        return {
            "signal": signal,
            "entry_type": entry_type,
            "entry_zone": [round(entry_low,2), round(entry_high,2)],
            "sl": round(sl,2),
            "tp1": round(tp1,2),
            "tp2": round(tp2,2),
            "tp3": round(tp3,2),
            "rr": round(rr,2),
            "confidence": confidence,
            "trend": trend,
            "status": status,
            "signal_time": signal_time,
            "reason": " | ".join(reason)
        }

    except:
        return {"signal": "ERROR", "reason": "Analysis failed"}


# ==============================
# API ROUTE
# ==============================
@app.get("/analyze")
def analyze():
    df_5m = get_binance_data("5m")
    df_15m = get_binance_data("15m")

    if df_5m.empty or df_15m.empty:
        return {"signal": "ERROR", "reason": "Data fetch failed"}

    trend_5m = get_trend(df_5m)
    trend_15m = get_trend(df_15m)

    if trend_5m != trend_15m:
        final_trend = trend_5m
        alignment = "NOT_ALIGNED"
    else:
        final_trend = trend_5m
        alignment = "ALIGNED"

    result = analyze_market(df_5m, final_trend)
    result["alignment"] = alignment

    return result
