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
        return {"status": "ERROR", "message": "Data fetch failed"}

    trend_1h = get_trend(df_1h)
    trend_15m = get_trend(df_15m)

    price = df_15m["close"].iloc[-2]

    high_15m, low_15m = get_levels(df_15m)

    # ==========================
    # DETERMINE PHASE
    # ==========================
    if trend_1h == trend_15m:
        phase = "IMPULSE"
    else:
        phase = "PULLBACK"

    result = {}

    # ==========================
    # IMPULSE (STRONG TREND)
    # ==========================
    if phase == "IMPULSE":

        if trend_1h == "UP":
            result["market_status"] = "UPTREND"
            result["current_move"] = "STRONG UP MOVE"
            result["what_to_do"] = "BUY NOW"

            result["entry"] = round(price, 2)
            result["target"] = round(high_15m, 2)
            result["stop_loss"] = round(low_15m, 2)

            result["message"] = "Market strong up. Buyers in control."

        else:
            result["market_status"] = "DOWNTREND"
            result["current_move"] = "STRONG DOWN MOVE"
            result["what_to_do"] = "SELL NOW"

            result["entry"] = round(price, 2)
            result["target"] = round(low_15m, 2)
            result["stop_loss"] = round(high_15m, 2)

            result["message"] = "Market strong down. Sellers in control."

    # ==========================
    # PULLBACK (MOST IMPORTANT)
    # ==========================
    else:

        if trend_1h == "DOWN":

            result["market_status"] = "DOWNTREND"
            result["current_move"] = "PULLBACK UP"

            result["what_to_do"] = "LOOK FOR SELL"

            result["sell_zone"] = [
                round(high_15m * 0.98, 2),
                round(high_15m, 2)
            ]

            result["current_price"] = round(price, 2)
            result["target"] = round(low_15m, 2)

            result["invalid_if_above"] = round(high_15m, 2)

            result["message"] = "Price is bouncing up in downtrend. Look for sell near top."

        else:

            result["market_status"] = "UPTREND"
            result["current_move"] = "PULLBACK DOWN"

            result["what_to_do"] = "LOOK FOR BUY"

            result["buy_zone"] = [
                round(low_15m, 2),
                round(low_15m * 1.02, 2)
            ]

            result["current_price"] = round(price, 2)
            result["target"] = round(high_15m, 2)

            result["invalid_if_below"] = round(low_15m, 2)

            result["message"] = "Price dipping in uptrend. Look for buy near bottom."

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
