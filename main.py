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
# FIBONACCI
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
# PRICE ACTION
# =========================
def detect_price_action(candles):
    last = candles[-1]
    prev = candles[-2]

    if prev["close"] > prev["open"] and last["close"] < last["open"] and last["open"] > prev["close"]:
        return "Bearish Engulfing"

    if prev["close"] < prev["open"] and last["close"] > last["open"] and last["open"] < prev["close"]:
        return "Bullish Engulfing"

    if last["high"] - max(last["open"], last["close"]) > (last["close"] - last["open"]) * 2:
        return "Upper Rejection Wick"

    if min(last["open"], last["close"]) - last["low"] > (last["close"] - last["open"]) * 2:
        return "Lower Rejection Wick"

    return "No strong pattern"

# =========================
# STRUCTURE
# =========================
def detect_structure(candles):
    highs = [c["high"] for c in candles[-5:]]
    lows = [c["low"] for c in candles[-5:]]

    if highs[-1] < highs[-2] and highs[-2] > highs[-3]:
        return "Lower High"

    if lows[-1] > lows[-2] and lows[-2] < lows[-3]:
        return "Higher Low"

    return "No clear structure"

# =========================
# SMC (BOS + CHOCH)
# =========================
def detect_smc(candles):
    highs = [c["high"] for c in candles[-10:]]
    lows = [c["low"] for c in candles[-10:]]

    last_high = highs[-1]
    prev_high = highs[-2]

    last_low = lows[-1]
    prev_low = lows[-2]

    if last_low < prev_low:
        return "BOS Down"

    if last_high > prev_high:
        return "BOS Up"

    if last_high > max(highs[:-1]):
        return "CHoCH Up"

    if last_low < min(lows[:-1]):
        return "CHoCH Down"

    return "No SMC signal"

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
    high_level = int(fib["high"])
    low_level = int(fib["low"])

    # Position
    if price < zone_low:
        position = "Below zone"
    elif zone_low <= price <= zone_high:
        position = "Inside zone"
    else:
        position = "Above zone"

    pattern = detect_price_action(c15)
    structure = detect_structure(c15)
    smc = detect_smc(c15)

    # =========================
    # LOGIC
    # =========================
    scenario = ""
    plan = ""
    entry = ""

    if trend1h == "DOWN" and trend15 == "UP":
        phase = "Bearish Pullback"
        bias = "Bearish"

        if position == "Inside zone":
            scenario = f"Sell zone active {zone_low}-{zone_high}"
            plan = f"Watch rejection at {zone_high}"

            if pattern in ["Bearish Engulfing", "Upper Rejection Wick"]:
                entry = f"SELL near {zone_high}"
            else:
                entry = "Wait"

        elif position == "Above zone":
            scenario = f"Liquidity sweep {zone_high}-{high_level}"

            if smc == "CHoCH Down" or structure == "Lower High":
                plan = f"Reversal confirmed below {zone_high}"
                entry = f"SELL after break below {zone_high}"
            elif smc == "BOS Up":
                plan = f"Breakout above {high_level}"
                entry = f"BUY above {high_level}"
            else:
                plan = f"Wait for structure below {zone_high}"
                entry = "No trade"

        else:
            scenario = f"Approaching sell zone {zone_low}-{zone_high}"
            plan = "Wait"
            entry = "No trade"

    else:
        phase = "Trend Continuation"
        bias = "Bullish" if trend1h == "UP" else "Bearish"
        scenario = "Trending"
        plan = "Follow trend"
        entry = "Trade with trend"

    return {
        "price": round(price, 2),
        "phase": phase,
        "bias": bias,
        "zone": f"{zone_low}-{zone_high}",
        "liquidity_zone": f"{zone_high}-{high_level}",
        "position": position,
        "pattern": pattern,
        "structure": structure,
        "smc_signal": smc,
        "scenario": scenario,
        "plan": plan,
        "entry": entry,
        "target": low_level,
        "invalidation": high_level,
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
