import os
import json
import yfinance as yf
from anthropic import Anthropic
from datetime import datetime

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

TRANSACTION_FEE = 2.0
PORTFOLIO_FILE = "portfolio.json"

WATCHLIST = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "AMD"]

def load_portfolio():
    with open(PORTFOLIO_FILE, "r") as f:
        return json.load(f)

def save_portfolio(portfolio):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(portfolio, f, indent=2)

def get_stock_prices(symbols):
    prices = {}
    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="1d", interval="1m")
            if not data.empty:
                prices[symbol] = round(float(data["Close"].iloc[-1]), 2)
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
    return prices

def calculate_portfolio_value(portfolio, prices):
    total = portfolio["cash"]
    for symbol, shares in portfolio["holdings"].items():
        if symbol in prices:
            total += shares * prices[symbol]
    return round(total, 2)

def ask_claude_for_decisions(portfolio, prices):
    holdings_detail = {}
    for symbol, shares in portfolio["holdings"].items():
        if symbol in prices:
            holdings_detail[symbol] = {
                "shares": shares,
                "current_price": prices[symbol],
                "current_value": round(shares * prices[symbol], 2)
            }

    portfolio_value = calculate_portfolio_value(portfolio, prices)

    prompt = f"""You are a day trading agent managing a stock portfolio.

Current Portfolio State:
- Cash available: ${portfolio['cash']:.2f}
- Total portfolio value: ${portfolio_value:.2f}
- Current holdings: {json.dumps(holdings_detail, indent=2)}

Current Market Prices:
{json.dumps(prices, indent=2)}

Transaction fee: ${TRANSACTION_FEE} per trade

Recent transaction history (last 5):
{json.dumps(portfolio['transaction_history'][-5:], indent=2)}

Based on current prices and portfolio state, decide what to buy and/or sell.
Rules:
- You can only buy stocks from this watchlist: {WATCHLIST}
- You cannot spend more cash than available (including $2 fee per trade)
- You cannot sell more shares than you own
- Aim to maximize profit over time
- You can hold, buy, sell, or do nothing

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
    return json.loads(raw)

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
        total_cost = round(shares * price + TRANSACTION_FEE, 2)
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

    print(f"\n📈 Fetching stock prices...")
    prices = get_stock_prices(WATCHLIST)
    print(f"Prices: {prices}")

    portfolio_value = calculate_portfolio_value(portfolio, prices)
    invested = round(portfolio_value - portfolio["cash"], 2)

    print(f"\n💰 Current portfolio value: ${portfolio_value}")
    print(f"   Cash: ${portfolio['cash']}")
    print(f"   Invested: ${invested}")
    print(f"   Holdings: {portfolio['holdings']}")

    holdings_with_value = {}
    for symbol, shares in portfolio["holdings"].items():
        price = prices.get(symbol, 0)
        holdings_with_value[symbol] = {
            "shares": shares,
            "price": price,
            "value": round(shares * price, 2)
        }

    print(f"\n🤖 Asking Claude for trading decisions...")
    result = ask_claude_for_decisions(portfolio, prices)

    print(f"\n📋 Strategy: {result['summary']}")

    if result["decisions"]:
        print(f"\n⚡ Executing {len(result['decisions'])} trade(s)...")
        executed = execute_trades(portfolio, result["decisions"], prices)

        for trade in executed:
            portfolio["transaction_history"].append({
                "timestamp": datetime.now().isoformat(),
                **trade
            })
    else:
        print("\n⏸️  No trades this cycle")

    portfolio["last_updated"] = datetime.now().isoformat()
    portfolio["total_value"] = calculate_portfolio_value(portfolio, prices)
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

    final_value = calculate_portfolio_value(portfolio, prices)
    print(f"\n📊 Final portfolio value: ${final_value}")
    print(f"   Cash: ${portfolio['cash']}")
    print(f"   Holdings: {portfolio['holdings']}")
    print(f"\n{'='*50}\n")

if __name__ == "__main__":
    main()
