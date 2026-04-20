from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
from datetime import datetime

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

def atr(candles, period=14):
    trs = []
    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i - 1]["close"]

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        trs.append(tr)

    atr_values = []
    for i in range(period, len(trs)):
        atr_values.append(sum(trs[i - period:i]) / period)

    return atr_values

# =========================
# SUPPORT / RESISTANCE
# =========================
def get_levels(candles):
    recent = candles[-50:]
    support = min(c["low"] for c in recent)
    resistance = max(c["high"] for c in recent)
    return support, resistance

# =========================
# KEY ZONE (WITH LEVELS)
# =========================
def get_key_zone(price, support, resistance, atr_val):
    res_level = round(resistance / 100) * 100
    sup_level = round(support / 100) * 100

    zone_range = int(atr_val)

    if abs(price - resistance) <= atr_val:
        return f"Sell zone: {res_level - zone_range} - {res_level}"

    elif abs(price - support) <= atr_val:
        return f"Buy zone: {sup_level} - {sup_level + zone_range}"

    elif support < price < resistance:
        return f"Mid range: {sup_level} - {res_level}"

    elif price > resistance:
        return f"Breakout above {res_level}"

    else:
        return f"Breakdown below {sup_level}"

# =========================
# MARKET EXPLANATION
# =========================
def explain_market(trend_1h, trend_15m, rsi_val, support, resistance, key_zone):
    res_level = round(resistance / 100) * 100
    sup_level = round(support / 100) * 100

    if trend_1h == "DOWN" and trend_15m == "UP":
        phase = "Bearish Pullback"
        dominance = "Sellers"
        move = "Short-term bullish retracement"
        next_move = f"Rejection near {res_level}"
        trap = "Buyers may get trapped"

    elif trend_1h == "UP" and trend_15m == "DOWN":
        phase = "Bullish Pullback"
        dominance = "Buyers"
        move = "Short-term bearish retracement"
        next_move = f"Bounce from {sup_level}"
        trap = "Sellers may get trapped"

    elif trend_1h == "UP" and trend_15m == "UP":
        phase = "Strong Uptrend"
        dominance = "Buyers"
        move = "Trend continuation"
        next_move = f"Break above {res_level}"
        trap = "Late sellers risk"

    else:
        phase = "Strong Downtrend"
        dominance = "Sellers"
        move = "Trend continuation"
        next_move = f"Break below {sup_level}"
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
        "key_zone": key_zone,
        "key_resistance": round(resistance, 2),
        "key_support": round(support, 2),
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
    atr_val = atr(c15)[-1]

    support, resistance = get_levels(c15)
    key_zone = get_key_zone(price, support, resistance, atr_val)

    trend_15 = "UP" if ema20_15 > ema50_15 else "DOWN"
    trend_1h = "UP" if ema20_1h > ema50_1h else "DOWN"

    action = "WAIT"

    if trend_1h == "UP" and trend_15 == "UP" and rsi_val > 55:
        action = "BUY"
    elif trend_1h == "DOWN" and trend_15 == "DOWN" and rsi_val < 45:
        action = "SELL"

    # Targets
    if action == "BUY":
        target = price + (2 * atr_val)
        sl = price - atr_val
    elif action == "SELL":
        target = price - (2 * atr_val)
        sl = price + atr_val
    else:
        target = price
        sl = price

    explanation = explain_market(
        trend_1h, trend_15, rsi_val, support, resistance, key_zone
    )

    return {
        "action": action,
        "entry": round(price, 2),
        "target": round(target, 2),
        "stoploss": round(sl, 2),
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
    "time": current_time.strftime("%H:%M:%S"),
    "market": "BTCUSDT",
    "signal": result
}

    except Exception as e:
        return {"error": str(e)}
