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
# TREND DETECTION
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
# SWING LEVELS
# ==============================
def get_levels(df):
    high = df["high"].tail(20).max()
    low = df["low"].tail(20).min()
    return high, low

# ==============================
# ANALYSIS
# ==============================
def analyze_market():

    df_1h = get_data("1h")
    df_15m = get_data("15m")

    if df_1h.empty or df_15m.empty:
        return {"error": "Data fetch failed"}

    trend_1h = get_trend(df_1h)
    trend_15m = get_trend(df_15m)

    price = df_15m["close"].iloc[-2]

    # Swing levels
    high_15m, low_15m = get_levels(df_15m)

    # ==========================
    # PHASE DETECTION
    # ==========================
    if trend_1h == trend_15m:
        phase = "IMPULSE"
    else:
        phase = "PULLBACK"

    # ==========================
    # LOGIC
    # ==========================

    result = {}

    # ==========================
    # CASE 1: IMPULSE
    # ==========================
    if phase == "IMPULSE":

        if trend_1h == "UP":
            result["market_trend"] = "UP"
            result["current_phase"] = "IMPULSE"
            result["action_now"] = "BUY NOW"
            result["entry"] = round(price, 2)
            result["primary_target"] = round(high_15m, 2)
            result["sl"] = round(low_15m, 2)
            result["reason"] = "Strong uptrend continuation"

        else:
            result["market_trend"] = "DOWN"
            result["current_phase"] = "IMPULSE"
            result["action_now"] = "SELL NOW"
            result["entry"] = round(price, 2)
            result["primary_target"] = round(low_15m, 2)
            result["sl"] = round(high_15m, 2)
            result["reason"] = "Strong downtrend continuation"

    # ==========================
    # CASE 2: PULLBACK (IMPORTANT)
    # ==========================
    else:

        if trend_1h == "DOWN":

            result["market_trend"] = "DOWN"
            result["current_phase"] = "PULLBACK"
            result["action_now"] = "SELL BIAS"
            result["entry"] = round(price, 2)

            result["pullback_zone"] = [
                round(high_15m * 0.98, 2),
                round(high_15m, 2)
            ]

            result["primary_target"] = round(low_15m, 2)

            result["if_rejection"] = "SELL CONTINUE"
            result["if_break"] = "TREND REVERSAL → BUY"

            result["reason"] = "Downtrend + pullback (look for sell)"

        else:

            result["market_trend"] = "UP"
            result["current_phase"] = "PULLBACK"
            result["action_now"] = "BUY BIAS"
            result["entry"] = round(price, 2)

            result["pullback_zone"] = [
                round(low_15m, 2),
                round(low_15m * 1.02, 2)
            ]

            result["primary_target"] = round(high_15m, 2)

            result["if_rejection"] = "BUY CONTINUE"
            result["if_break"] = "TREND REVERSAL → SELL"

            result["reason"] = "Uptrend + dip (look for buy)"

    # ==========================
    # EXTRA INFO
    # ==========================
    result["trend_1h"] = trend_1h
    result["trend_15m"] = trend_15m
    result["time"] = datetime.datetime.now().strftime("%H:%M:%S")

    return result


# ==============================
# API
# ==============================
@app.get("/analyze")
def get_analysis():
    return analyze_market()
