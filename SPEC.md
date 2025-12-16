# Trading System Spec v1 (US Equities, Daily, News-driven)

## Market
- Venue: US equities (NYSE/Nasdaq), regular session only.
- Regular session: 9:30 a.m.–4:00 p.m. ET.
- Cadence: Daily.
- Decision protocol (Option A):
  - Decision time: configurable (default 10:00 a.m. ET).
  - Feature cutoff: include only news with published_time <= decision_time.
  - Execution: enter/exit at same-day close (4:00 p.m. ET close), simulated.

## Universe
- Universe: S&P 500 constituents (prototype uses current membership snapshot).
- Membership refresh: monthly snapshot.

## Strategy constraints
- Long/short allowed.
- Shorting constraints:
  - Borrow fee modeled (flat annualized placeholder in v1).
  - Optional “no borrow available” failure mode (configurable).

## News sources
- Allowlist only (see sources_allowlist.yml).
- v1 uses free RSS sources:
  - BBC RSS
  - SEC RSS (structured disclosure)
  - (optional) Yahoo Finance RSS patterns

## Execution & costs (v1 placeholders)
- Commission model: configurable per-share or per-trade.
- Spread/slippage: configurable; enforced in simulator later (Step 3).

## Risk ("self-destruct")
- Daily loss limit: configurable (liquidate + lockout for the day).
- Max drawdown: configurable (liquidate + stop experiment).
- Max gross exposure, max net exposure, max single-name exposure.
