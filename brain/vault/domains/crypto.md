---
title: Crypto Domain Knowledge
tags: [domain, crypto]
buildings: [crypto_trading, market_data, btc_recovery]
personas: [crypto_operator, full_multistream]
priority: 2
---

# Crypto Domain

## Crypto Trading
- Use ccxt against the configured exchange. Respect position sizing and stop rules.
- Publish `trade.closed` on fill so Finance can mark PnL.

## Market Data
- Snapshot prices on a cadence; fuel trading + treasury decisions.

## BTC Recovery
- Recover value from owned/partially-owned addresses and UTXOs. High-sensitivity:
  never expose private keys in logs or the Brain.
