---
title: Crypto Domain Knowledge
tags: [domain, crypto]
buildings: [crypto_trading, market_data]
personas: [crypto_operator, full_multistream]
priority: 2
---

# Crypto Domain

## Crypto Trading
- Use ccxt against the configured exchange. Respect position sizing and stop rules.
- Publish `trade.closed` on fill so Finance can mark PnL.

## Market Data
- Snapshot prices on a cadence; fuel trading + treasury decisions.
