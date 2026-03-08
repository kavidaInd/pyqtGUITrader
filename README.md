# Trading Assistant — Personal Automated Options Trader

A fully autonomous trading assistant for Indian equity options (NIFTY, BANKNIFTY, FINNIFTY).  
Supports 10 brokers, live/paper/backtest modes, and runs as a native desktop application on Windows, macOS, and Linux.

---

## Features

| Feature | Details |
|---------|---------|
| **Brokers** | Fyers, Zerodha, Dhan, Angel One, Upstox, Shoonya, Kotak Neo, ICICI Breeze, Alice Blue, FlatTrade |
| **Trading Modes** | Live, Paper (simulation), Backtest |
| **Strategy Engine** | Rule-based dynamic signal engine with confidence scoring |
| **Risk Controls** | TP %, SL %, Trailing SL, Index SL, Max Hold Bars, Max Daily Loss, Max Trades/Day |
| **Options** | ATM CE/PE, weekly & monthly expiry, auto expiry selection |
| **Backtest** | Bar-by-bar replay with Black-Scholes option pricing, per-candle debug log |
| **Caching** | Indicator results cached per candle-close — no redundant calculations on every tick |
| **Platforms** | Windows 10+, macOS 11+, Ubuntu 20.04+ |

---

## Quick Start

### Option 1 — Run from source (development)

```bash
# 1. Clone / unzip the project
cd TradingGUI

# 2. Create a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# 3. Install with your broker SDK
pip install ".[fyers]"          # Fyers only
pip install ".[zerodha]"        # Zerodha only
pip install ".[all-brokers]"    # every broker SDK

# 4. Run
python main.py
```

### Option 2 — Install as a system package

```bash
python scripts/build.py --install
trading-assistant              # launch from any terminal
```

### Option 3 — Build a native distributable executable

```bash
python scripts/build.py --exe
# Output: dist/TradingAssistant/TradingAssistant.exe  (Windows)
#         dist/TradingAssistant.app                   (macOS)
#         dist/TradingAssistant/TradingAssistant       (Linux)
```

---

## Installation Requirements

| Requirement | Minimum Version |
|------------|----------------|
| Python | 3.10 |
| PyQt5 | 5.15 |
| pandas | 2.0 |
| requests | 2.31 |
| SQLAlchemy | 2.0 |

Broker-specific SDKs are **optional** — install only the one(s) you use.

---

## Configuration

On first launch the app creates:

```
Data/           ← log files
config/         ← config.json, token cache, strategy files
backups/        ← automatic config backups
```

### config/config.json structure

```json
{
  "brokerage": {
    "broker_type": "fyers",
    "client_id": "YOUR_APP_ID",
    "secret_key": "YOUR_SECRET",
    "redirect_uri": "http://127.0.0.1:8000/broker/fyers"
  },
  "daily": {
    "derivative": "NIFTY50-INDEX",
    "lot_size": 75,
    "history_interval": "5m"
  },
  "pnl": {
    "profit_type": "TRAILING",
    "tp_percentage": 30.0,
    "stoploss_percentage": 15.0
  },
  "mode": {
    "mode": "Paper",
    "paper_balance": 100000.0
  }
}
```

---

## Platform-Specific Notes

### Windows
- The `.exe` shows no console window (`--noconsole` in PyInstaller).
- A Start-Menu shortcut is created by the optional NSIS installer (`scripts/make_installer_win.nsi`).

### macOS
- The `.app` bundle is **not notarised by default**.  To notarise: set `codesign_identity` in the spec and run `xcrun notarytool`.
- macOS 11+ required (arm64 and x86_64 supported; use `--target-arch universal2` in PyInstaller for a fat binary).

### Linux
- Requires `libxcb-xinerama0` and Qt5 platform plugins on the host:  
  `sudo apt install libxcb-xinerama0 libqt5gui5`
- AppImage packaging script: `scripts/make_appimage.sh` (requires `appimagetool`).

---

## Backtest Cache

The backtest engine caches indicator calculations keyed by `(symbol, timeframe, df_fingerprint)`.  
The cache is invalidated automatically on each candle-close, so:

- **Same candle, multiple evaluations** → second call is ~free (returns cached result)
- **New candle** → recalculates fresh indicators, stores result

To force a full cache clear programmatically:

```python
broker.invalidate_cache()           # all symbols
broker.invalidate_cache("NIFTY")   # one symbol only
```

---

## Changelog

### 1.0.0 (refactored)
- `BaseEnums`: replaced loose string constants with proper `Enum` classes; removed 12 redundant validation functions.
- `BaseBroker`: added sliding-window rate limiter, exponential-backoff retry, per-symbol indicator cache, `invalidate_cache()`.
- `BrokerFactory`: single `_BROKER_META` dict replaces three duplicated dicts; lazy-import of broker modules.
- `BacktestEngine`: `_PositionTracker` class eliminates scattered local variables; signal evaluation is cached; `_close_trade` returns a `NamedTuple`; `_get_historical_option_symbol` is memoised.
- `BacktestThread`: removed 250-line dead `__main__` test block; early `stop()` now honoured before engine creation.
- Added `pyproject.toml`, `trading_assistant.spec`, and `scripts/build.py` for cross-platform packaging.