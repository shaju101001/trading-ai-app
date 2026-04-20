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
# INDICATORS
# =========================
def ema(values, period):
    k = 2 / (period + 1)
    ema_val = values[0]
    for price in values[1:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val

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
# FIB LEVELS
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
# ADAPTIVE DECISION ENGINE
# =========================
def build_decision(c15, c1h):
    closes15 = [c["close"] for c in c15]
    closes1h = [c["close"] for c in c1h]

    price = closes15[-1]

    # Trend
    trend15 = "UP" if ema(closes15, 20) > ema(closes15, 50) else "DOWN"
    trend1h = "UP" if ema(closes1h, 20) > ema(closes1h, 50) else "DOWN"

    # Momentum
    rsi_val = rsi(closes15)

    # Fib zone
    fib = get_fib(c15)
    zone_low = int(fib["fib618"])
    zone_high = int(fib["fib50"])

    # =========================
    # POSITION CHECK
    # =========================
    if price < zone_low:
        position = "Below zone"
    elif zone_low <= price <= zone_high:
        position = "Inside zone"
    else:
        position = "Above zone"

    # =========================
    # CORE LOGIC
    # =========================
    phase = ""
    bias = ""
    plan = ""
    entry = ""
    target = ""
    invalid = ""
    scenario = ""

    # ===== BEARISH PULLBACK CASE =====
    if trend1h == "DOWN" and trend15 == "UP":
        phase = "Bearish Pullback"
        bias = "Bearish"

        if position == "Below zone":
            plan = "Price moving toward sell zone"
            entry = "Wait"

        elif position == "Inside zone":
            plan = "Watch for rejection"
            entry = "Sell after bearish candle"

        else:
            # 🔥 NEW ADAPTIVE LOGIC
            if rsi_val > 60:
                scenario = "Possible bullish breakout"
                plan = "Reversal possible"
                entry = "Wait for pullback buy setup"
            else:
                scenario = "Weak breakout"
                plan = "Wait for re-entry into zone"
                entry = "Sell on retest"

        target = int(fib["low"])
        invalid = int(fib["high"])

    # ===== BULLISH PULLBACK =====
    elif trend1h == "UP" and trend15 == "DOWN":
        phase = "Bullish Pullback"
        bias = "Bullish"

        if position == "Below zone":
            scenario = "Breakdown risk"
            plan = "Wait for recovery"
            entry = "No trade"

        elif position == "Inside zone":
            plan = "Watch for bounce"
            entry = "Buy after bullish candle"

        else:
            scenario = "Strong breakout"
            plan = "Trend continuation"
            entry = "Buy pullbacks"

        target = int(fib["high"])
        invalid = int(fib["low"])

    # ===== STRONG TREND =====
    else:
        if trend1h == "UP":
            phase = "Strong Uptrend"
            bias = "Bullish"
            plan = "Buy dips"
            entry = "Buy on pullback"
            target = int(fib["high"])
            invalid = int(fib["low"])
        else:
            phase = "Strong Downtrend"
            bias = "Bearish"
            plan = "Sell rallies"
            entry = "Sell on bounce"
            target = int(fib["low"])
            invalid = int(fib["high"])

    # Momentum label
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
