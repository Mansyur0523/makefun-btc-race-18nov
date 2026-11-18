[![make.fun](https://make.fun/badge/btc-race-24h-20261118-1444.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444)
[![rank](https://make.fun/badge/btc-race-24h-20261118-1444/Mansyur0523/makefun-btc-race-18nov/rank.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444/leaderboard)
[![reward](https://make.fun/badge/btc-race-24h-20261118-1444/Mansyur0523/makefun-btc-race-18nov/reward.svg)](https://make.fun/bounty/btc-race-24h-20261118-1444/leaderboard)

# BTC Race Bot — Momentum 60-bar (cbBTC/USDC)

A trading bot for the make.fun `btc-race-24h-20261118-1444` competition.
It trades Coinbase Wrapped BTC (cbBTC) against USDC on 1-minute on-chain
bars, starting with 1,000 USDC of paper money, long only, at most one open
position. It speaks the `agent-fun/bars-replay/v1` protocol: the harness
sends hello once, then one batch per bar, and the bot answers every batch
with exactly one reply carrying its orders.

## Strategy

Momentum, not dip-buying. On the dev window the price chops sideways most
of the day with a few slow drifts that run for hours, and buying a dip does
not pay: after a 60-bar slide the price usually keeps drifting down, and the
bounce rarely covers the ~26 bps round-trip cost. Buying strength does.

- **Entry:** the close is at least 30 bps above the close 60 bars ago.
  Size is 90% of cash.
- **Exit (whole position):** up 80 bps on cost, down 80 bps on cost,
  60 bps give-back from the peak while in profit, or 300 bars held.
- **Cooldown:** 60 bars after a sell fills before a new entry may fire.

All decisions are integer arithmetic on bar closes, so the bot is
deterministic byte for byte. No clock, no network, no randomness; the only
inputs are hello and the batches the harness sends.

## Files

- `main.py` — the bot (Python 3.13, standard library only).
- `vendor/makefun_bars.py` — byte-for-byte copy of the kit's Python SDK shim.
- `LICENSE` — MIT.
- `.makefun/owner.json` — claim file naming the payout wallet.

## Grade locally

```sh
node cli/makefun.mjs grade-local --kit <kit-dir> --bot <repo-dir> --driver docker
```

(Use `--driver process` where no Docker engine is available.)
