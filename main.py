from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
from datetime import datetime
import pytz

app = FastAPI()

# CORS
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
async def get_binance_data(interval="5m", limit=150):
    params = {
        "symbol": "BTCUSDT",
        "interval": interval,
        "limit": limit
    }

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(BINANCE_URL, params=params)
        r.raise_for_status()
        data = r.json()

    candles = []
    for d in data:
        candles.append({
            "open": float(d[1]),
            "high": float(d[2]),
            "low": float(d[3]),
            "close": float(d[4]),
            "volume": float(d[5])
        })

    return candles

# =========================
# INDICATORS
# =========================
def ema(values, period):
    k = 2 / (period + 1)
    ema_values = [values[0]]
    for price in values[1:]:
        ema_values.append(price * k + ema_values[-1] * (1 - k))
    return ema_values

def rsi(values, period=14):
    gains, losses = [], []

    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    rsis = [50] * period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        rs = avg_gain / avg_loss if avg_loss != 0 else 0
        rsis.append(100 - (100 / (1 + rs)))

    return rsis

# =========================
# FIBONACCI LEVELS
# =========================
def get_fib_levels(candles):
    recent = candles[-50:]

    high = max(c["high"] for c in recent)
    low = min(c["low"] for c in recent)

    diff = high - low

    fib_50 = high - (0.5 * diff)
    fib_618 = high - (0.618 * diff)

    return {
        "high": high,
        "low": low,
        "fib_50": fib_50,
        "fib_618": fib_618
    }

# =========================
# MARKET EXPLANATION
# =========================
def explain_market(trend_1h, trend_15m, rsi_val, fib):
    fib_50 = fib["fib_50"]
    fib_618 = fib["fib_618"]

    zone_low = int(fib_618)
    zone_high = int(fib_50)

    if trend_1h == "DOWN" and trend_15m == "UP":
        phase = "Bearish Pullback"
        dominance = "Sellers"
        move = "Short-term bullish retracement"
        next_move = f"Rejection likely in Fib zone {zone_low} - {zone_high}"
        trap = "Buyers may get trapped"

    elif trend_1h == "UP" and trend_15m == "DOWN":
        phase = "Bullish Pullback"
        dominance = "Buyers"
        move = "Short-term bearish retracement"
        next_move = f"Bounce likely in Fib zone {zone_low} - {zone_high}"
        trap = "Sellers may get trapped"

    elif trend_1h == "UP" and trend_15m == "UP":
        phase = "Strong Uptrend"
        dominance = "Buyers"
        move = "Trend continuation"
        next_move = f"Break above {int(fib['high'])}"
        trap = "Late sellers risk"

    else:
        phase = "Strong Downtrend"
        dominance = "Sellers"
        move = "Trend continuation"
        next_move = f"Break below {int(fib['low'])}"
        trap = "Late buyers risk"

    # RSI classification
    if rsi_val > 65:
        momentum = "Strong bullish"
    elif rsi_val > 55:
        momentum = "Mild bullish"
    elif rsi_val < 35:
        momentum = "Strong bearish"
    elif rsi_val < 45:
        momentum = "Mild bearish"
    else:
        momentum = "Neutral"

    return {
        "market_phase": phase,
        "dominance": dominance,
        "current_move": move,
        "momentum": momentum,
        "next_probability": next_move,
        "key_zone": f"Fib zone: {zone_low} - {zone_high}",
        "fib_50": round(fib_50, 2),
        "fib_618": round(fib_618, 2),
        "trap_warning": trap
    }

# =========================
# SIGNAL ENGINE
# =========================
def generate_signal(c15, c1h):
    closes_15 = [c["close"] for c in c15]
    closes_1h = [c["close"] for c in c1h]

    price = closes_15[-1]

    ema20_15 = ema(closes_15, 20)[-1]
    ema50_15 = ema(closes_15, 50)[-1]
    ema20_1h = ema(closes_1h, 20)[-1]
    ema50_1h = ema(closes_1h, 50)[-1]

    rsi_val = rsi(closes_15)[-1]

    fib = get_fib_levels(c15)

    trend_15 = "UP" if ema20_15 > ema50_15 else "DOWN"
    trend_1h = "UP" if ema20_1h > ema50_1h else "DOWN"

    explanation = explain_market(trend_1h, trend_15, rsi_val, fib)

    return {
        "price": round(price, 2),
        "trend_1h": trend_1h,
        "trend_15m": trend_15,
        "rsi": round(rsi_val, 2),
        "market_explanation": explanation
    }

# =========================
# API ROUTES
# =========================
@app.get("/")
def home():
    return {"status": "API running"}

@app.get("/analyze")
async def analyze():
    try:
        c15 = await get_binance_data("15m")
        c1h = await get_binance_data("1h")

        result = generate_signal(c15, c1h)

        ist = pytz.timezone("Asia/Kolkata")
        current_time = datetime.now(ist)

        return {
            "time": current_time.strftime("%d-%m-%Y %H:%M:%S IST"),
            "market": "BTCUSDT",
            "data": result
        }

    except Exception as e:
        return {"error": str(e)}
