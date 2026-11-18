"""Momentum bot for the cbBTC/USDC 1-minute race (agent-fun/bars-replay/v1).

The bot speaks the protocol through the vendored shim: it receives hello
once, then one batch per bar, and answers every batch with exactly one reply
carrying its orders (at most one order here). Every decision is integer
arithmetic on the closes of the bars seen so far, so two runs on the same
bars produce the same orders byte for byte. No clock, no network, no
randomness: the only inputs are hello and the batches the harness sends.

Idea, from the dev window's own shape: on 1-minute bars this market chops
sideways most of the day, with a few slow drifts that run for hours. Buying
a dip does not pay here -- after a 60-bar slide the price usually keeps
drifting down, and the bounce the old dip bot waited for rarely covers the
~26 bps round-trip cost. Buying strength does: when the close has risen at
least 30 bps over the last 60 bars, the drift tends to carry a little
further, enough to clear the fee, slippage and impact of a round trip.
So the bot does very little:

  * It stays in cash until the close is up at least 30 bps on the close
    60 bars ago (a slow drift up, not a one-minute spike).
  * It buys 90% of cash, never all of it: a full-size fill moves its own
    price about 7 bps on this pool, so a slightly smaller size is cheaper
    per trade, and it keeps a cash buffer for the fee.
  * It sells the whole position when it is up 80 bps on cost, down 80 bps,
    gives back 60 bps from its peak while still in profit, or after 300
    bars held, whichever comes first. A dead position is closed by the
    clock, not nursed to the end of the window.
  * After a sell fills it waits 60 bars before a new entry may fire, so
    the same drift is not bought straight back while it is already fading.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bars

SYMBOL = "CBBTC"

# Entry: the close must be at least this many bps above the close
# LOOKBACK_BARS bars ago.
LOOKBACK_BARS = 60
RISE_BPS = 30

# Size: share of cash committed on each entry (basis points).
SIZE_BPS = 9000

# Exits, in basis points against the position's cost (fees included).
TAKE_PROFIT_BPS = 80
STOP_BPS = 80
# Give-back from the best close since entry that ends a winning trade.
TRAIL_BPS = 60
# Longest a position is held, in bars, whatever the price does.
MAX_HOLD_BARS = 300
# Bars to wait after a sell filled before a new entry may fire.
COOLDOWN_BARS = 60

# A fill more than this far from the close it was decided on is refused by
# the replay; 1% is far above any 1-minute move in the dev window (max 63 bps)
# plus the modelled slippage and impact, so a refused order is simply retried
# on the next bar while its reason still holds.
MAX_SLIPPAGE_BPS = 100

BPS = 10000


class MomentumBot:
    """Keeps the close history and the open position's bookkeeping."""

    def __init__(self):
        # Closes seen so far, oldest first, as ints at the symbol's price scale.
        self.closes = []
        # Bar count (in closes) when the current position first appeared, and
        # the best close since then; None while flat.
        self.entry_len = None
        self.peak = None
        # Bar count when the last position disappeared (a sell filled). A new
        # entry needs COOLDOWN_BARS after it, so a drift that already faded
        # is not bought straight back on the next bar.
        self.sell_len = None
        self._was_holding = False

    def on_batch(self, state, batch):
        if state.warming_up:
            return []
        close = state.close(SYMBOL)
        if close is None:
            return []
        self.closes.append(close)
        holding = state.positions.get(SYMBOL)
        qty = holding.qty if holding is not None else 0

        if qty > 0:
            self._was_holding = True
            return self._maybe_exit(state, holding, close)
        if self._was_holding:
            # The position is gone: the sell filled on this bar's open.
            self.sell_len = len(self.closes)
            self._was_holding = False
        self.entry_len = None
        self.peak = None
        return self._maybe_enter(state, close)

    def _maybe_enter(self, state, close):
        n = len(self.closes)
        if n <= LOOKBACK_BARS:
            return []
        if self.sell_len is not None and n - self.sell_len < COOLDOWN_BARS:
            return []
        # Rise over the last LOOKBACK_BARS bars:
        # close >= close_60 * (1 + 30 bps).
        base = self.closes[n - 1 - LOOKBACK_BARS]
        if close * BPS < base * (BPS + RISE_BPS):
            return []
        notional = state.cash * SIZE_BPS // BPS
        min_notional = int(state.hello["fees"]["min_notional_quote_units"])
        if notional < min_notional or notional <= 0:
            return []
        if notional > state.cash:
            notional = state.cash
        return [
            {
                "side": "buy",
                "symbol": SYMBOL,
                "notional_quote_units": notional,
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            }
        ]

    def _maybe_exit(self, state, holding, close):
        if self.entry_len is None:
            # The position appeared (a buy filled); start the clock here.
            self.entry_len = len(self.closes)
            self.peak = close
        if close > self.peak:
            self.peak = close
        value = state.value(SYMBOL, holding.qty)
        cost = holding.cost
        sell = False
        if value * BPS >= cost * (BPS + TAKE_PROFIT_BPS):
            sell = True  # up 80 bps on cost
        elif value * BPS <= cost * (BPS - STOP_BPS):
            sell = True  # down 80 bps on cost
        elif value > cost and self.peak * BPS > close * (BPS + TRAIL_BPS):
            sell = True  # gave back 60 bps from the peak while ahead
        elif len(self.closes) - self.entry_len >= MAX_HOLD_BARS:
            sell = True  # held too long; close it and wait for the next drift
        if not sell:
            return []
        return [
            {
                "side": "sell",
                "symbol": SYMBOL,
                "qty": holding.qty,
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            }
        ]


makefun_bars.run(MomentumBot().on_batch)
