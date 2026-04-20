from fastapi import FastAPI
import requests
import pandas as pd
import numpy as np
import datetime

app = FastAPI()

# ==============================
# FETCH DATA
# ==============================
def get_data(interval):
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": "BTCUSDT", "interval": interval, "limit": 100}
        res = requests.get(url, params=params, timeout=10)

        if res.status_code != 200:
            return pd.DataFrame()

        data = res.json()
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
        if df["close"].iloc[-2] > df["close"].iloc[-10]:
            return "UP"
        else:
            return "DOWN"
    except:
        return "SIDEWAYS"


# ==============================
# DAY RANGE POSITION
# ==============================
def get_day_position(df):
    try:
        high = df["high"].max()
        low = df["low"].min()
        price = df["close"].iloc[-2]

        pos = (price - low) / (high - low)

        if pos > 0.7:
            return "NEAR_HIGH"
        elif pos < 0.3:
            return "NEAR_LOW"
        else:
            return "MIDDLE"
    except:
        return "UNKNOWN"


# ==============================
# MARKET CONDITION
# ==============================
def get_market_condition(df):
    try:
        high = df["high"].max()
        low = df["low"].min()

        if (high - low) < (df["close"].iloc[-1] * 0.003):
            return "SIDEWAYS"
        else:
            return "TRENDING"
    except:
        return "UNKNOWN"


# ==============================
# MAIN ANALYSIS
# ==============================
def analyze():
    df_1h = get_data("1h")
    df_15m = get_data("15m")

    if df_1h.empty or df_15m.empty:
        return {"status": "ERROR", "reason": "Data fetch failed"}

    trend_1h = get_trend(df_1h)
    trend_15m = get_trend(df_15m)

    price = df_15m["close"].iloc[-2]

    day_high = df_15m["high"].max()
    day_low = df_15m["low"].min()

    position = get_day_position(df_15m)
    market = get_market_condition(df_15m)

    # ==========================
    # DECISION LOGIC
    # ==========================
    action = "WAIT"
    target = price
    sl = price
    probability = 50
    reason = []

    if market == "SIDEWAYS":
        return {
            "action": "WAIT",
            "market_condition": "SIDEWAYS",
            "reason": "Low movement market"
        }

    # BUY LOGIC
    if trend_1h == "UP" and trend_15m == "UP":
        if position != "NEAR_HIGH":
            action = "BUY NOW"
            target = day_high
            sl = day_low
            probability = 65
            reason.append("Uptrend + momentum")

    # SELL LOGIC
    elif trend_1h == "DOWN" and trend_15m == "DOWN":
        if position != "NEAR_LOW":
            action = "SELL NOW"
            target = day_low
            sl = day_high
            probability = 65
            reason.append("Downtrend + momentum")

    else:
        action = "WAIT"
        probability = 40
        reason.append("Trend mismatch")

    return {
        "action": action,
        "current_price": round(price, 2),
        "target": round(target, 2),
        "sl": round(sl, 2),
        "probability": probability,
        "trend_1h": trend_1h,
        "trend_15m": trend_15m,
        "market_condition": market,
        "day_position": position,
        "reason": " | ".join(reason),
        "time": datetime.datetime.now().strftime("%H:%M:%S")
    }


# ==============================
# API
# ==============================
@app.get("/analyze")
def get_analysis():
    return analyze()
