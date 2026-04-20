from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
from datetime import datetime
import pytz

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BINANCE_URL = "https://api.binance.com/api/v3/klines"

# =========================
# FETCH DATA
# =========================
async def get_binance_data(interval="15m", limit=150):
    params = {"symbol": "BTCUSDT", "interval": interval, "limit": limit}

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(BINANCE_URL, params=params)
        r.raise_for_status()
        data = r.json()

    return [{
        "open": float(d[1]),
        "high": float(d[2]),
        "low": float(d[3]),
        "close": float(d[4]),
    } for d in data]

# =========================
# EMA
# =========================
def ema(values, period):
    k = 2 / (period + 1)
    ema_val = values[0]
    for price in values[1:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val

# =========================
# RSI
# =========================
def rsi(values, period=14):
    gains, losses = [], []
    for i in range(1, len(values)):
        diff = values[i] - values[i-1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain*(period-1)+gains[i])/period
        avg_loss = (avg_loss*(period-1)+losses[i])/period

    rs = avg_gain / avg_loss if avg_loss != 0 else 0
    return 100 - (100/(1+rs))

# =========================
# FIB
# =========================
def get_fib(candles):
    high = max(c["high"] for c in candles[-50:])
    low = min(c["low"] for c in candles[-50:])
    diff = high - low

    return {
        "high": high,
        "low": low,
        "fib50": high - 0.5 * diff,
        "fib618": high - 0.618 * diff
    }

# =========================
# PRICE ACTION DETECTION
# =========================
def detect_price_action(candles):
    last = candles[-1]
    prev = candles[-2]

    # Bearish engulfing
    if prev["close"] > prev["open"] and last["close"] < last["open"] and last["open"] > prev["close"]:
        return "Bearish Engulfing"

    # Bullish engulfing
    if prev["close"] < prev["open"] and last["close"] > last["open"] and last["open"] < prev["close"]:
        return "Bullish Engulfing"

    # Rejection wick (upper)
    if last["high"] - max(last["open"], last["close"]) > (last["close"] - last["open"]) * 2:
        return "Upper Rejection Wick"

    # Rejection wick (lower)
    if min(last["open"], last["close"]) - last["low"] > (last["close"] - last["open"]) * 2:
        return "Lower Rejection Wick"

    return "No strong pattern"

# =========================
# DECISION ENGINE
# =========================
def build_decision(c15, c1h):
    closes15 = [c["close"] for c in c15]
    closes1h = [c["close"] for c in c1h]

    price = closes15[-1]

    trend15 = "UP" if ema(closes15, 20) > ema(closes15, 50) else "DOWN"
    trend1h = "UP" if ema(closes1h, 20) > ema(closes1h, 50) else "DOWN"

    rsi_val = rsi(closes15)
    fib = get_fib(c15)

    zone_low = int(fib["fib618"])
    zone_high = int(fib["fib50"])

    # Position
    if price < zone_low:
        position = "Below zone"
    elif zone_low <= price <= zone_high:
        position = "Inside zone"
    else:
        position = "Above zone"

    # Price action
    pattern = detect_price_action(c15)

    scenario = ""
    plan = ""
    entry = ""

    # =========================
    # ADAPTIVE LOGIC
    # =========================

    if trend1h == "DOWN" and trend15 == "UP":
        phase = "Bearish Pullback"
        bias = "Bearish"

        if position == "Inside zone":
            if pattern in ["Bearish Engulfing", "Upper Rejection Wick"]:
                scenario = "Confirmed rejection"
                plan = "Sell confirmed"
                entry = "Enter SELL"
            else:
                scenario = "Waiting confirmation"
                plan = "Watch for rejection"
                entry = "No trade"

        elif position == "Above zone":
            if price > fib["high"]:
                scenario = "Confirmed breakout"
                plan = "Trend shift possible"
                entry = "Buy pullback"
            else:
                scenario = "Liquidity sweep"
                plan = "Watch for rejection back into zone"
                entry = "Sell if price drops below zone"

        else:
            scenario = "Approaching zone"
            plan = "Wait"
            entry = "No trade"

        target = int(fib["low"])
        invalid = int(fib["high"])

    else:
        phase = "Trend Continuation"
        bias = "Bullish" if trend1h == "UP" else "Bearish"
        scenario = "Trending"
        plan = "Trade with trend"
        entry = "Follow trend"
        target = int(fib["high"] if bias == "Bullish" else fib["low"])
        invalid = int(fib["low"] if bias == "Bullish" else fib["high"])

    # Momentum
    if rsi_val > 65:
        momentum = "Strong bullish"
    elif rsi_val < 35:
        momentum = "Strong bearish"
    else:
        momentum = "Neutral"

    return {
        "price": round(price, 2),
        "phase": phase,
        "bias": bias,
        "momentum": momentum,
        "zone": f"{zone_low} - {zone_high}",
        "position": position,
        "pattern": pattern,
        "scenario": scenario,
        "plan": plan,
        "entry": entry,
        "target": target,
        "invalidation": invalid,
        "trend_1h": trend1h,
        "trend_15m": trend15
    }

# =========================
# API
# =========================
@app.get("/analyze")
async def analyze():
    try:
        c15 = await get_binance_data("15m")
        c1h = await get_binance_data("1h")

        decision = build_decision(c15, c1h)

        ist = pytz.timezone("Asia/Kolkata")
        now = datetime.now(ist)

        return {
            "time": now.strftime("%d-%m-%Y %H:%M:%S IST"),
            "market": "BTCUSDT",
            "decision": decision
        }

    except Exception as e:
        return {"error": str(e)}
