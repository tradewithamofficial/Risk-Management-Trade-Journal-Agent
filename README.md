# Trade With AM — Risk Management & Trade Journal Agent

**[Official repository](https://github.com/tradewithamofficial/Risk-Management-Trade-Journal-Agent) · [Windows v1.0.0 download](https://github.com/tradewithamofficial/Risk-Management-Trade-Journal-Agent/releases/tag/v1.0.0) · [ChatGPT Master Prompt](docs/CHATGPT_MASTER_PROMPT.md)**

V1 is a Windows CustomTkinter risk calculator and **local** trade-record manager.
It reuses the dark UI/dialog style and read-only TradingView watchlist/local model
catalogue readers from the SMC agent. Existing agents are not changed.

## What V1 does

- Add, edit and delete exchange **display names** with a fixed USD Starting Capital.
  Initial examples: Binance ($10,000) and Bybit Demo ($5,000).
- Choose a TradingView symbol from the existing watchlist or enter one manually.
  The selected exchange is a label; its name need not match the symbol's prefix.
- Size LONG/SHORT ideas using a 0.1%–9.9% risk slider in 0.1% steps (default 1.0%).
  At 5.0% or more the capital card turns red and confirmation repeats the warning.
- Calculate on Enter and whenever risk, exchange or direction changes.
- Record a trade after confirmation. **Execute Trade records locally; it does not
  submit an order.** Active status changes only through a manual record edit.
- Edit direction, entry, stop, risk, status, exit price, manually supplied final
  P&L, strategy and notes. Move completed records into the Completed Trades tab.
- Delete a local record only after confirmation. Both tables scroll horizontally
  and vertically; click the ⚙ cell, double-click a row, or select it and press Enter.
- View Trade Journal and Generate Reports show their requested Version 2 placeholders.
  The adjacent model dropdown reads your local catalogue but never runs AI.

## Calculations and assumptions

Assume a **linear USD-quoted instrument with contract multiplier 1**:

```text
Risk USD = Starting Capital × Risk Percentage / 100
Stop Distance = abs(Entry Price − Stop Loss Price)
Position Quantity = Risk USD / Stop Distance
Position Notional = Position Quantity × Entry Price
Minimum whole-number leverage = max(1, ceil(Position Notional / Starting Capital))
Estimated margin = Position Notional / Minimum whole-number leverage
```

LONG requires stop below entry; SHORT requires stop above entry. All three prices
(including optional exit) and capital must be positive finite values. P&L can be
positive, zero or negative and is entered manually. Invalid/incomplete values show
an error instead of recording a trade. Direction is never silently reversed.

Calculation uses Decimal with 80-digit intermediate precision and an integer
ceiling for leverage. Inputs accept up to 28 significant digits and decimal
magnitudes from 10^-28 through below 10^29; stored results retain Decimal strings.
USD displays round to cents; quantity displays round to eight decimal places.
These display formats are not broker quantity/price increments.

**Leverage and margin are estimates**, not broker eligibility or liquidation
calculations. Contract specifications, lot steps, fees, slippage, funding,
liquidation risk and margin rules are not included. No balance is fetched.

## Exchange Settings and credential handling

Exchange Settings contains Display name, Starting Capital, Enable Live Trading,
API Key, masked API Secret and API URL. Checking Enable Live Trading enables those
three inputs; unchecking disables them. **These are presentation-only controls in
V1. Their contents are not read by storage, saved, transmitted or logged.** They
are cleared on save/cancel/close and when changing the exchange being edited.
Checking the box does not authorize or execute a trade. Do not enter real secrets.

Only the display name and fixed Starting Capital are saved as exchange settings,
along with the internal ID and created/updated timestamps. There are no API
credential columns, live-mode flag persistence, API clients or exchange requests.

Starting Capital does not change when a trade is recorded/completed or a P&L is
entered. Editing capital affects future calculations and trades only. Each trade
keeps its original capital/exchange-name snapshot; later trade edits recalculate
against that original capital. Deleting an exchange preserves all its trade history.

## Local storage and privacy

SQLite (Python's built-in sqlite3) stores exchanges and trades. Default location:

```text
%LOCALAPPDATA%\TradeWithAM\RiskManagementTradeJournalAgent\journal.sqlite3
```

If LOCALAPPDATA is absent, the fallback is
`~/.local/share/TradeWithAM/RiskManagementTradeJournalAgent/journal.sqlite3`.
Storage is independent of the working directory and any future PyInstaller
temporary folder. Entry/completion and exchange timestamps are timezone-aware UTC.
Trade money/quantity fields use TEXT Decimal representations, not SQLite floats.

The database is local and unencrypted; treat it and backups as private. Close the
app before copying a backup. Database files, credentials, environments, logs and
private results are excluded by `.gitignore`. No Telegram or AI report is sent.

## Windows v1.0.0 — no Python required

Download `RiskManagementTradeJournalAgent-v1.0.0-windows-x64.zip` from the official
GitHub Release linked above. Extract the **entire ZIP** into a writable folder and
run `RiskManagementTradeJournalAgent/RiskManagementTradeJournalAgent.exe`.
Keep `_internal`, the documentation and license notices with the EXE. The package
includes Python/Tkinter and its UI dependencies; Python, PyCharm and Codex are
not required for risk calculations and local records.

The EXE uses the project's final gold robot icon. It is unsigned; verify the
official release and SHA-256 rather than disabling Windows security protections.
Optional TradingView assets need your existing TradingView Desktop debug/CDP
connection, Node.js and TradingView MCP setup. Optional model selection reads a
local Codex catalogue; it does not execute AI. No exchange credential is required.

Start with [INSTALL.md](INSTALL.md) or copy the complete viewer-facing
[ChatGPT Master Prompt](docs/CHATGPT_MASTER_PROMPT.md) into a new ChatGPT chat
for one-step-at-a-time setup and optional customization guidance.

## Run in PyCharm / from source

Open this independent project and create/select its `.venv` interpreter. Use
Windows Python with Tkinter (the reference environment uses Python 3.14):

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

In PyCharm run `main.py` with the project `.venv\Scripts\python.exe` interpreter.
No special working directory is needed for user-data storage. For a disposable
database, use `python main.py --database path/to/test.sqlite3`.

The calculator/database do not require an exchange account, Codex invocation or
TradingView connection. Optional watchlist discovery uses your existing Node.js
and TradingView MCP setup; default connector: `%USERPROFILE%\tradingview-mcp`.
The reused `SR_TRADINGVIEW_MCP_DIR`, `SR_NODE_PATH` and `SR_SYMBOLS` environment
overrides remain supported. Refresh only reads the existing watchlist; it does
not switch charts, symbols or timeframes or create drawings. If unavailable,
fallback/manual symbols remain usable. All Charts is visible but disabled since
a local record has exactly one asset. Model selection reads the existing local
Codex catalogue; an absent catalogue does not prevent local trade recording.

## Not implemented in V1

No exchange API authentication/connections, live or demo orders, balance retrieval,
position/status synchronization, price polling, automatic stops or closure,
exchange-based P&L calculation, AI execution/reports, journal pages, chart drawings
or Telegram. Future exchange-specific demo work must be separately designed and
authorized; the API-looking controls do not implement that capability.

## Offline verification and future customization

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Tests use temporary databases and mocked external readers/network. They cover
calculator rules, static capital and history, CRUD/restart persistence, GUI startup,
confirmation/high-risk behavior, selectors, placeholders, and nonpersistence of API
fields. No live analysis, exchange connection, TradingView mutation or Telegram is
needed. The release build is verified separately with isolated test user data; no personal
database is bundled. Build instructions are below.

See the [final setup/customization Master Prompt](docs/CHATGPT_MASTER_PROMPT.md).
Future work can extend the local journal, reports and separately approved demo
integrations without changing this release's local-only meaning of Execute Trade.

MIT project license. The final owner-supplied gold icon, reused dialogs and pinned UI dependencies follow the
existing agent's asset locations; see [notices](THIRD-PARTY-NOTICES.md).

## Build from source

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

This uses the same pinned PyInstaller onedir process as the previous agents.
Preserve/move an existing release folder before rebuilding. No saved database,
session, API configuration or private trading record belongs in the package.
The user-data database location remains the same for source and EXE: upgrading
or extracting a new application folder does not reset trades. Back up the entire
user-data folder while the application is closed; do not replace it with test data.

See [release notes](docs/RELEASE-v1.0.0.md). Future demo API integrations, richer
journal pages and AI reports are optional new development, not hidden V1 features.
