from fastapi import FastAPI, Query
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
# FETCH BTC
# =========================
async def get_binance_data(interval="15m", limit=150):
    params = {"symbol": "BTCUSDT", "interval": interval, "limit": limit}

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(BINANCE_URL, params=params)
        data = r.json()

    return [{
        "open": float(d[1]),
        "high": float(d[2]),
        "low": float(d[3]),
        "close": float(d[4]),
    } for d in data]

# =========================
# FETCH XAU (TwelveData)
# =========================
async def get_xauusd_data(interval="15min"):
    API_KEY = "31e678aa26d440aabf509abae13717fe"

    url = f"https://api.twelvedata.com/time_series?symbol=XAU/USD&interval={interval}&outputsize=200&apikey={API_KEY}"

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url)
        data = r.json()

    if "values" not in data:
        raise Exception("XAU fetch failed")

    candles = []
    for d in reversed(data["values"]):
        candles.append({
            "open": float(d["open"]),
            "high": float(d["high"]),
            "low": float(d["low"]),
            "close": float(d["close"]),
        })

    return candles

# =========================
# EMA
# =========================
def ema(values, period):
    k = 2 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e

# =========================
# FIB
# =========================
def get_fib(candles):
    high = max(c["high"] for c in candles[-50:])
    low = min(c["low"] for c in candles[-50:])
    diff = high - low

    return {
        "high": int(high),
        "low": int(low),
        "fib50": int(high - 0.5 * diff),
        "fib618": int(high - 0.618 * diff)
    }

# =========================
# STRUCTURE
# =========================
def detect_structure(c):
    highs = [x["high"] for x in c[-5:]]
    lows = [x["low"] for x in c[-5:]]

    if highs[-1] < highs[-2] and highs[-2] > highs[-3]:
        return "Lower High"
    if lows[-1] > lows[-2] and lows[-2] < lows[-3]:
        return "Higher Low"

    return "No structure"

# =========================
# SMC
# =========================
def detect_smc(c):
    highs = [x["high"] for x in c[-10:]]
    lows = [x["low"] for x in c[-10:]]

    if lows[-1] < lows[-2]:
        return "BOS Down"
    if highs[-1] > highs[-2]:
        return "BOS Up"

    if highs[-1] > max(highs[:-1]):
        return "CHoCH Up"
    if lows[-1] < min(lows[:-1]):
        return "CHoCH Down"

    return "No SMC"

# =========================
# REAL LIQUIDITY SWEEP
# =========================
def detect_sweep(c, zone_high):
    prev = c[-2]
    last = c[-1]

    breakout = prev["high"] > zone_high
    rejection = last["close"] < zone_high

    return breakout and rejection

# =========================
# ENGINE
# =========================
def build_decision(c15, c1h):
    closes15 = [x["close"] for x in c15]
    closes1h = [x["close"] for x in c1h]

    price = closes15[-1]

    trend15 = "UP" if ema(closes15, 20) > ema(closes15, 50) else "DOWN"
    trend1h = "UP" if ema(closes1h, 20) > ema(closes1h, 50) else "DOWN"

    fib = get_fib(c15)

    zone_low = fib["fib618"]
    zone_high = fib["fib50"]
    high_level = fib["high"]
    low_level = fib["low"]

    # POSITION
    if price < zone_low:
        position = "Below"
    elif price <= zone_high:
        position = "Inside"
    else:
        position = "Above"

    structure = detect_structure(c15)
    smc = detect_smc(c15)
    sweep = detect_sweep(c15, zone_high)

    # =========================
    # LOGIC
    # =========================
    if trend1h == "DOWN" and trend15 == "UP":
        phase = "Bearish Pullback"
        bias = "Bearish"

        if position == "Above":

            if sweep:
                scenario = f"Sweep at {zone_high}"

                if structure == "Lower High" or smc == "CHoCH Down":
                    entry = f"SELL below {zone_high}"
                else:
                    entry = "Wait confirmation"

            elif smc == "BOS Up":
                scenario = "Breakout"
                entry = f"BUY above {high_level}"

            else:
                scenario = "Weak breakout"
                entry = "Wait"

        elif position == "Inside":
            scenario = "Sell zone"
            entry = f"SELL near {zone_high}"

        else:
            scenario = "Approaching"
            entry = "Wait"

    else:
        phase = "Trend"
        bias = "Bullish" if trend1h == "UP" else "Bearish"

        if bias == "Bullish":
            entry = f"BUY above {zone_low}"
        else:
            entry = f"SELL below {zone_high}"

        scenario = "Trend continuation"

    # =========================
    # TARGET FIX
    # =========================
    if "BUY" in entry:
        target = int(high_level * 1.002)
    elif "SELL" in entry:
        target = int(low_level * 0.998)
    else:
        target = 0

    return {
        "price": round(price, 2),
        "phase": phase,
        "bias": bias,
        "zone": f"{zone_low}-{zone_high}",
        "liquidity_zone": f"{zone_high}-{high_level}",
        "position": position,
        "structure": structure,
        "smc": smc,
        "scenario": scenario,
        "entry": entry,
        "target": target,
        "invalidation": high_level
    }

# =========================
# API
# =========================
@app.get("/analyze")
async def analyze(symbol: str = Query("BTCUSDT")):
    try:
        if symbol == "BTCUSDT":
            c15 = await get_binance_data("15m")
            c1h = await get_binance_data("1h")

        elif symbol == "XAUUSD":
            c15 = await get_xauusd_data("15min")
            c1h = await get_xauusd_data("1h")

        else:
            return {"error": "Invalid symbol"}

        decision = build_decision(c15, c1h)

        now = datetime.now(pytz.timezone("Asia/Kolkata"))

        return {
            "time": now.strftime("%d-%m-%Y %H:%M:%S IST"),
            "market": symbol,
            "decision": decision
        }

    except Exception as e:
        return {"error": str(e)}
