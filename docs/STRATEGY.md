# Strategy — Institutional Smart Money Confluence

ZeroTrace FX AI trades **with institutional order flow or not at all**.
Every entry needs stacked confirmation; anything missing means HOLD.

## Multi-timeframe stack

| TF | Role |
|---|---|
| D1 | Macro trend / institutional direction |
| H4 | Primary trend / major liquidity |
| H1 | Market structure: BOS, CHoCH, swings |
| M15 | Setup confirmation: OB / FVG / sweep |
| M5 | Execution timing + live pricing |

Single-timeframe entries are impossible by construction: the checklists read
D1, H4, H1 and M15 together.

## Smart Money Concepts (all candle-based, no indicators-as-signals)

- Fractal **swing highs/lows** (external + internal scopes)
- **BOS** (trend continuation) and **CHoCH** (trend flip) from closing breaks
- **Order blocks**: last opposite candle before ATR displacement legs, scored
  by displacement size, structure-break overlap and freshness
- **Fair value gaps** with fill tracking and invalidation on body closes through
- **Liquidity sweeps** (wick beyond swing, close back inside) with displacement bonus
- **Equal highs/lows** pools, **supply/demand** zones, **premium/discount**
  dealing-range positioning, mitigation % and invalidation everywhere

## BUY checklist (SELL mirrors)

1. D1 macro bias bullish
2. H4 primary trend bullish
3. H1 bullish BOS or CHoCH within `STRUCTURE_RECENCY_BARS`
4. Price in **discount** or at a bullish OB / demand zone
5. Sell-side liquidity swept below within `SWEEP_RECENCY_BARS`
6. Bullish FVG aligned (fresh or at the entry zone)
7. HTF trend confirmation
8. Spread within `SPREAD_LIMIT_PIPS`
9. No high-impact news blackout

## AI confidence score (0–100)

Each passing direction is scored by 11 weighted components
(weights sum to 100, threshold default **85**):

HTF trend 18 · structure 12 · BOS 10 · CHoCH 8 · OB quality 12 ·
FVG quality 8 · sweep 10 · volatility 5 · session 5 · spread 5 · momentum 7.

Every contribution and the PASS/REJECT verdict are written to the journal —
no black boxes.

## Exits and basket

- ATR stop-loss (`ATR_SL_MULT`, default 1.5×) with minimum RR 1:2
- Break-even lock, trailing stop and one partial take-profit per position
- **Basket target**: the instant combined floating profit hits `BASKET_TARGET`,
  *all* positions close, pending orders cancel, stats reset
- **Trailing basket** (optional): once the target is reached, the basket rides
  with a `BASKET_TRAILING_PCT` give-back and closes on the trail level

## Risk doctrine

1% risk per trade, dynamic sizing from stop distance and contract specs,
max positions/lots, daily/weekly loss limits, max drawdown, consecutive-loss
lock, spread/latency filters and an emergency kill switch. Capital preservation
outranks opportunity, always.
