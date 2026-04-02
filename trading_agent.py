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
