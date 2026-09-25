# Development status — 2026-09-25

## Current state
- Shared payload models already provide distinct `TradingSignalIntentSpot`/`TradingSignalSpot` and futures variants. SPOT models reject SHORT direction, while BUY/SELL remains a separate action axis. No code changes or live contract rollout have been made in this checkout.

## Needed for the fractals objective
- Define or version a wallet-agnostic percentage signal with explicit SPOT/FUTURES identity, stable strategy/trade/signal IDs, price/validity, and separate Binance/FA route outcome identities. Keep backward-compatible decoding during rollout.
- Verify framework, fractals, validator, Binance bridge and Operations consume the same contract before enabling hot execution.

## Dependencies and risk
- A signal is not an order or fill. Do not put physical Binance balance or manual holdings in the strategy signal contract. UAT/PROD usage is not verified here.
