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
# FETCH XAU
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
def get_fib(c):
    high = max(x["high"] for x in c[-50:])
    low = min(x["low"] for x in c[-50:])
    diff = high - low

    return {
        "high": int(high),
        "low": int(low),
        "fib50": int(high - 0.5 * diff),
        "fib618": int(high - 0.618 * diff)
    }

# =========================
# LIQUIDITY
# =========================
def get_liquidity_level(c):
    highs = [x["high"] for x in c[-20:]]
    return int(max(highs[:-1]))

# =========================
# SWEEP
# =========================
def detect_sweep(c, liquidity_level):
    prev = c[-2]
    last = c[-1]

    breakout = prev["high"] > liquidity_level
    rejection = last["close"] < liquidity_level

    return breakout and rejection

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

    return "None"

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

    return "None"

# =========================
# PRESSURE (KEY FEATURE)
# =========================
def detect_pressure(c):
    last = c[-1]
    prev = c[-2]

    body = abs(last["close"] - last["open"])
    rng = last["high"] - last["low"]

    momentum = last["close"] - c[-3]["close"]
    strength = body / rng if rng != 0 else 0

    if last["close"] > last["open"] and strength > 0.6 and momentum > 0:
        return "Bullish Strong"

    if last["close"] < last["open"] and strength > 0.6 and momentum < 0:
        return "Bearish Strong"

    if momentum > 0:
        return "Bullish Weak"

    if momentum < 0:
        return "Bearish Weak"

    return "Neutral"

# =========================
# ENGINE
# =========================
def build_decision(data):
    c1m = data["1m"]
    c5m = data["5m"]
    c15 = data["15m"]
    c1h = data["1h"]

    price = c15[-1]["close"]

    closes15 = [x["close"] for x in c15]
    closes1h = [x["close"] for x in c1h]

    trend15 = "UP" if ema(closes15, 20) > ema(closes15, 50) else "DOWN"
    trend1h = "UP" if ema(closes1h, 20) > ema(closes1h, 50) else "DOWN"

    fib = get_fib(c15)

    zone_low = fib["fib618"]
    zone_high = fib["fib50"]
    high_level = fib["high"]
    low_level = fib["low"]

    liquidity = get_liquidity_level(c15)
    sweep = detect_sweep(c15, liquidity)

    structure = detect_structure(c15)
    smc = detect_smc(c15)

    # PRESSURE
    p1m = detect_pressure(c1m)
    p5m = detect_pressure(c5m)
    p15m = detect_pressure(c15)
    p1h = detect_pressure(c1h)

    # =========================
    # ENTRY LOGIC (SCALPER)
    # =========================
    entry = "WAIT"
    scenario = "No setup"

    if sweep and ("Bearish" in p1m or "Bearish" in p5m):
        scenario = f"Sweep at {liquidity}"
        entry = f"SELL below {zone_high}"

    elif sweep and ("Bullish" in p1m or "Bullish" in p5m):
        scenario = f"Sweep reversal up at {liquidity}"
        entry = f"BUY above {zone_low}"

    elif smc == "BOS Down" and "Bearish" in p5m:
        scenario = "Bearish continuation"
        entry = f"SELL below {zone_high}"

    elif smc == "BOS Up" and "Bullish" in p5m:
        scenario = "Bullish continuation"
        entry = f"BUY above {high_level}"

    # =========================
    # TARGET
    # =========================
    if "BUY" in entry:
        target = int(price + (high_level - price) * 0.5)
    elif "SELL" in entry:
        target = int(price - (price - low_level) * 0.5)
    else:
        target = 0

    return {
        "price": round(price, 2),
        "zone": f"{zone_low}-{zone_high}",
        "liquidity": liquidity,
        "structure": structure,
        "smc": smc,
        "pressure": {
            "1m": p1m,
            "5m": p5m,
            "15m": p15m,
            "1h": p1h
        },
        "scenario": scenario,
        "entry": entry,
        "target": target
    }

# =========================
# API
# =========================
@app.get("/analyze")
async def analyze(symbol: str = Query("BTCUSDT")):
    try:
        if symbol == "BTCUSDT":
            data = {
                "1m": await get_binance_data("1m"),
                "5m": await get_binance_data("5m"),
                "15m": await get_binance_data("15m"),
                "1h": await get_binance_data("1h"),
            }

        elif symbol == "XAUUSD":
            data = {
                "1m": await get_xauusd_data("1min"),
                "5m": await get_xauusd_data("5min"),
                "15m": await get_xauusd_data("15min"),
                "1h": await get_xauusd_data("1h"),
            }

        else:
            return {"error": "Invalid symbol"}

        decision = build_decision(data)

        now = datetime.now(pytz.timezone("Asia/Kolkata"))

        return {
            "time": now.strftime("%d-%m-%Y %H:%M:%S IST"),
            "market": symbol,
            "decision": decision
        }

    except Exception as e:
        return {"error": str(e)}
