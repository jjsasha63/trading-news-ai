from live_broker import LivePaperBroker

b = LivePaperBroker()
print("Equity:", b.get_portfolio_value())
positions = b.list_positions()
if positions:
    print("Positions:")
    for p in positions:
        print(f"  {p.symbol}: {p.qty} shares @ ${p.current_price:.2f} = ${float(p.market_value):.2f}")
else:
    print("No positions")
