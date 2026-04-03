import os
import json
import re
import yfinance as yf
import pandas as pd
from anthropic import Anthropic
from datetime import datetime

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

TRANSACTION_FEE = 2.0
PORTFOLIO_FILE = "portfolio.json"
TOP_MOVERS_COUNT = 20

def load_portfolio():
    with open(PORTFOLIO_FILE, "r") as f:
        return json.load(f)

def save_portfolio(portfolio):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(portfolio, f, indent=2)

def get_sp500_tickers():
    sources = [
        "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv",
        "https://datahub.io/core/s-and-p-500-companies/r/constituents.csv"
    ]
    for url in sources:
        try:
            df = pd.read_csv(url)
            tickers = df["Symbol"].str.replace(".", "-", regex=False).tolist()
            print(f"✅ Fetched {len(tickers)} S&P 500 tickers")
            return tickers
        except Exception as e:
            print(f"Source failed ({url}): {e}")
            continue
    print("All sources failed, using fallback list")
    return [
        "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMD", "TSLA", "AMZN",
        "JPM", "BAC", "GS", "V", "MA", "JNJ", "PFE", "UNH", "ABBV",
        "XOM", "CVX", "WMT", "MCD", "COST", "NKE", "SPY", "QQQ"
    ]

def bulk_fetch_prices_and_movers(tickers, holdings):
    print(f"📦 Bulk downloading price history for {len(tickers)} stocks...")
    try:
        data = yf.download(
            tickers,
            period="3mo",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True
        )
    except Exception as e:
        print(f"Bulk download failed: {e}")
        return {}, []

    movers = []
    current_prices = {}

    for symbol in tickers:
        try:
            if len(tickers) == 1:
                hist_close = data["Close"]
                hist_volume = data["Volume"]
            else:
                if symbol not in data.columns.get_level_values(0):
                    continue
                hist_close = data[symbol]["Close"]
                hist_volume = data[symbol]["Volume"]

            hist_close = hist_close.dropna()
            hist_volume = hist_volume.dropna()

            if len(hist_close) < 2:
                continue

            current_price = round(float(hist_close.iloc[-1]), 2)
            prev_price = round(float(hist_close.iloc[-2]), 2)
            current_prices[symbol] = current_price

            if prev_price > 0:
                change_pct = round(((current_price - prev_price) / prev_price) * 100, 2)
                movers.append({
                    "symbol": symbol,
                    "change_pct": change_pct,
                    "current_price": current_price,
                    "hist_close": hist_close.tolist(),
                    "hist_volume": hist_volume.tolist()
                })
        except Exception:
            continue

    movers.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
    top_movers = movers[:TOP_MOVERS_COUNT]

    holding_data = []
    for symbol in holdings:
        if symbol in current_prices:
            existing = next((m for m in movers if m["symbol"] == symbol), None)
            if existing and existing not in top_movers:
                holding_data.append(existing)
            elif not existing:
                holding_data.append({
                    "symbol": symbol,
                    "change_pct": 0,
                    "current_price": current_prices[symbol],
                    "hist_close": [],
                    "hist_volume": []
                })

    combined = top_movers + holding_data
    combined = list({d["symbol"]: d for d in combined}.values())

    print(f"✅ Bulk download complete — {len(current_prices)} prices, {len(combined)} stocks for analysis")
    return current_prices, combined

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calculate_indicators(symbol, hist_close, hist_volume, in_portfolio):
    try:
        closes = [float(x) for x in hist_close]
        volumes = [float(x) for x in hist_volume]

        if len(closes) < 2:
            return None

        current_price = round(closes[-1], 2)

        ma7  = round(sum(closes[-7:])  / min(7,  len(closes)), 2) if len(closes) >= 7  else None
        ma20 = round(sum(closes[-20:]) / min(20, len(closes)), 2) if len(closes) >= 20 else None
        ma50 = round(sum(closes[-50:]) / min(50, len(closes)), 2) if len(closes) >= 50 else None

        rsi = calculate_rsi(closes)

        avg_vol_10d = round(sum(volumes[-10:]) / min(10, len(volumes)), 0) if len(volumes) >= 10 else None
        volume_ratio = round(volumes[-1] / avg_vol_10d, 2) if avg_vol_10d and avg_vol_10d > 0 else None

        high_52w = round(max(closes[-252:]), 2) if len(closes) >= 252 else round(max(closes), 2)
        low_52w  = round(min(closes[-252:]), 2) if len(closes) >= 252 else round(min(closes), 2)

        momentum_7d  = round(((current_price - closes[-7])  / closes[-7])  * 100, 2) if len(closes) >= 7  else None
        momentum_30d = round(((current_price - closes[-30]) / closes[-30]) * 100, 2) if len(closes) >= 30 else None

        return {
            "symbol": symbol,
            "in_portfolio": in_portfolio,
            "current_price": current_price,
            "ma7": ma7,
            "ma20": ma20,
            "ma50": ma50,
            "rsi": rsi,
            "volume_ratio": volume_ratio,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "momentum_7d_pct": momentum_7d,
            "momentum_30d_pct": momentum_30d
        }
    except Exception as e:
        print(f"Error calculating indicators for {symbol}: {e}")
        return None

def calculate_portfolio_value(portfolio, prices):
    total = portfolio["cash"]
    for symbol, shares in portfolio["holdings"].items():
        if symbol in prices:
            total += shares * prices[symbol]
    return round(total, 2)

def ask_claude_for_decisions(portfolio, prices, watchlist_with_indicators):
    holdings_detail = {}
    for symbol, shares in portfolio["holdings"].items():
        if symbol in prices:
            holdings_detail[symbol] = {
                "shares": shares,
                "current_price": prices[symbol],
                "current_value": round(shares * prices[symbol], 2)
            }

    portfolio_value = calculate_portfolio_value(portfolio, prices)
    available_symbols = [w["symbol"] for w in watchlist_with_indicators]

    prompt = f"""You are a day trading agent managing a stock portfolio.

Current Portfolio State:
- Cash available: ${portfolio['cash']:.2f}
- Total portfolio value: ${portfolio_value:.2f}
- Current holdings: {json.dumps(holdings_detail, indent=2)}

Transaction fee: ${TRANSACTION_FEE} per trade

Recent transaction history (last 5):
{json.dumps(portfolio['transaction_history'][-5:], indent=2)}

Top market movers today with technical indicators:
{json.dumps(watchlist_with_indicators, indent=2)}

Technical indicator guide:
- RSI above 70 = overbought (consider selling), below 30 = oversold (consider buying)
- Price above MA20/MA50 = bullish trend, below = bearish
- Volume ratio above 1.5 = unusually high volume (strong signal)
- Momentum = recent price change percentage

Based on this data, decide what to buy and/or sell.
Rules:
- You can ONLY buy stocks from this exact list: {available_symbols}
- You cannot spend more cash than available (including ${TRANSACTION_FEE} fee per trade)
- You cannot sell more shares than you own
- Aim to maximize profit over time
- Consider RSI, moving averages, momentum and volume in your decisions

Respond ONLY with a valid JSON object in this exact format:
{{
  "decisions": [
    {{"action": "buy", "symbol": "AAPL", "shares": 2, "reason": "..."}},
    {{"action": "sell", "symbol": "TSLA", "shares": 1, "reason": "..."}}
  ],
  "summary": "Brief summary of your strategy this cycle"
}}

If no action needed, return decisions as an empty array with a summary explaining why."""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        matches = re.findall(r'\{.*?\}', raw, re.DOTALL)
        for match in matches:
            try:
                parsed = json.loads(match)
                if "decisions" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue

        start = raw.find('{')
        end = raw.rfind('}')
        if start != -1 and end != -1:
            try:
                return json.loads(raw[start:end+1])
            except json.JSONDecodeError:
                pass

        print(f"Warning: Could not parse response, returning empty decisions. Raw: {raw[:200]}")
        return {"decisions": [], "summary": "Could not parse Claude response, skipping cycle"}

def execute_trades(portfolio, decisions, prices):
    executed = []

    for decision in decisions:
        action = decision["action"]
        symbol = decision["symbol"]
        shares = decision["shares"]

        if symbol not in prices:
            print(f"Skipping {symbol} - price not available")
            continue

        price = prices[symbol]
        total_cost    = round(shares * price + TRANSACTION_FEE, 2)
        total_revenue = round(shares * price - TRANSACTION_FEE, 2)

        if action == "buy":
            if portfolio["cash"] >= total_cost:
                portfolio["cash"] = round(portfolio["cash"] - total_cost, 2)
                portfolio["holdings"][symbol] = portfolio["holdings"].get(symbol, 0) + shares
                executed.append({**decision, "price": price, "total": total_cost})
                print(f"✅ BUY {shares} {symbol} @ ${price} | Total: ${total_cost}")
            else:
                print(f"❌ Skipping BUY {symbol} - insufficient funds")

        elif action == "sell":
            owned = portfolio["holdings"].get(symbol, 0)
            if owned >= shares:
                portfolio["cash"] = round(portfolio["cash"] + total_revenue, 2)
                portfolio["holdings"][symbol] = owned - shares
                if portfolio["holdings"][symbol] == 0:
                    del portfolio["holdings"][symbol]
                executed.append({**decision, "price": price, "total": total_revenue})
                print(f"✅ SELL {shares} {symbol} @ ${price} | Revenue: ${total_revenue}")
            else:
                print(f"❌ Skipping SELL {symbol} - not enough shares")

    return executed

def main():
    print(f"\n{'='*50}")
    print(f"Trading Agent Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")

    portfolio = load_portfolio()
    print(f"\n📂 Portfolio loaded")

    print(f"\n🔍 Fetching S&P 500 tickers...")
    all_tickers = get_sp500_tickers()

    print(f"\n📦 Bulk fetching prices and finding top movers...")
    current_prices, top_stocks = bulk_fetch_prices_and_movers(all_tickers, list(portfolio["holdings"].keys()))

    print(f"\n🔬 Calculating technical indicators for {len(top_stocks)} stocks...")
    watchlist_with_indicators = []
    for stock in top_stocks:
        indicators = calculate_indicators(
            stock["symbol"],
            stock["hist_close"],
            stock["hist_volume"],
            stock["symbol"] in portfolio["holdings"]
        )
        if indicators:
            watchlist_with_indicators.append(indicators)

    portfolio_value = calculate_portfolio_value(portfolio, current_prices)
    invested = round(portfolio_value - portfolio["cash"], 2)

    print(f"\n💰 Current portfolio value: ${portfolio_value}")
    print(f"   Cash: ${portfolio['cash']}")
    print(f"   Invested: ${invested}")
    print(f"   Holdings: {portfolio['holdings']}")

    holdings_with_value = {}
    for symbol, shares in portfolio["holdings"].items():
        price = current_prices.get(symbol, 0)
        holdings_with_value[symbol] = {
            "shares": shares,
            "price": price,
            "value": round(shares * price, 2)
        }

    print(f"\n🤖 Asking Claude for trading decisions...")
    result = ask_claude_for_decisions(portfolio, current_prices, watchlist_with_indicators)

    print(f"\n📋 Strategy: {result['summary']}")

    if result["decisions"]:
        print(f"\n⚡ Executing {len(result['decisions'])} trade(s)...")
        executed = execute_trades(portfolio, result["decisions"], current_prices)
        for trade in executed:
            portfolio["transaction_history"].append({
                "timestamp": datetime.now().isoformat(),
                **trade
            })
    else:
        print("\n⏸️  No trades this cycle")

    portfolio["last_strategy"] = result.get("summary", "No strategy available")
    portfolio["last_decisions"] = result.get("decisions", [])
    portfolio["total_value"] = calculate_portfolio_value(portfolio, current_prices)
    portfolio["invested"] = round(portfolio["total_value"] - portfolio["cash"], 2)
    portfolio["holdings_with_value"] = holdings_with_value

    portfolio["value_history"] = portfolio.get("value_history", [])
    portfolio["value_history"].append({
        "timestamp": datetime.now().isoformat(),
        "total_value": portfolio["total_value"],
        "cash": portfolio["cash"],
        "invested": portfolio["invested"]
    })

    save_portfolio(portfolio)

    print(f"\n📊 Final portfolio value: ${portfolio['total_value']}")
    print(f"   Cash: ${portfolio['cash']}")
    print(f"   Holdings: {portfolio['holdings']}")
    print(f"\n{'='*50}\n")

if __name__ == "__main__":
    main()
