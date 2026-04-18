from fastapi import FastAPI
import requests
import pandas as pd
import numpy as np
import datetime

app = FastAPI()

# ==============================
# FETCH DATA (SAFE)
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

        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)

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
# LIQUIDITY
# ==============================
def detect_liquidity(df):
    try:
        highs = df["high"].tail(10).values
        lows = df["low"].tail(10).values

        liquidity_above = np.std(highs) < 10
        liquidity_below = np.std(lows) < 10

        return liquidity_above, liquidity_below
    except:
        return False, False


# ==============================
# ANALYSIS
# ==============================
def analyze_market(df, trend):
    try:
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

        # SIGNAL
        if trend == "UP":
            signal = "BUY"
            sl = support
            risk = max(price - sl, 1)  # prevent zero

            entry_low = support
            entry_high = support + (risk * 0.3)

            tp1 = price + (risk * rr1)
            tp2 = price + (risk * rr2)
            tp3 = price + (risk * rr3)

            confidence += 30
            reason.append("Uptrend setup")

            if liquidity_below:
                confidence += 20
                reason.append("Liquidity below")

        else:
            signal = "SELL"
            sl = resistance + 10
            risk = max(sl - price, 1)

            entry_low = resistance - (risk * 0.3)
            entry_high = resistance

            tp1 = price - (risk * rr1)
            tp2 = price - (risk * rr2)
            tp3 = price - (risk * rr3)

            confidence += 30
            reason.append("Downtrend setup")

            if liquidity_above:
                confidence += 20
                reason.append("Liquidity above")

        # STATUS
        if price < entry_low:
            status = "WAIT"
        elif entry_low <= price <= entry_high:
            status = "ENTER NOW"
        else:
            status = "MISSED"

        # RR SAFE
        if abs(entry_low - sl) > 0:
            rr = abs(tp1 - entry_low) / abs(entry_low - sl)
        else:
            rr = 0

        signal_time = datetime.datetime.now().strftime("%H:%M:%S")

        # STRENGTH
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
            "rr": round(rr,2),
            "confidence": confidence,
            "trend": trend,
            "status": status,
            "signal_time": signal_time,
            "reason": " | ".join(reason)
        }

    except:
        return {
            "signal": "ERROR",
            "reason": "Analysis failed"
        }


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

    # ALWAYS GIVE SIGNAL
    if trend_5m != trend_15m:
        final_trend = trend_5m
        alignment = "NOT_ALIGNED"
        penalty = 20
    else:
        final_trend = trend_5m
        alignment = "ALIGNED"
        penalty = 0

    result = analyze_market(df_5m, final_trend)

    if "confidence" in result:
        result["confidence"] = max(0, result["confidence"] - penalty)

    result["alignment"] = alignment

    return result
