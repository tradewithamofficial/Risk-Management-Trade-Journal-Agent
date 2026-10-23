# Install and use v1.0.0

Official repository: https://github.com/tradewithamofficial/Risk-Management-Trade-Journal-Agent

## Windows package

1. Download the Windows x64 ZIP from https://github.com/tradewithamofficial/Risk-Management-Trade-Journal-Agent/releases/tag/v1.0.0.
2. Extract the complete folder and launch `RiskManagementTradeJournalAgent.exe`.
   Keep `_internal` and documentation/notices beside it. Python is bundled.
3. Use an exchange display name and fixed Starting Capital. Enter LONG/SHORT,
   entry/stop prices and risk, then press Enter. Leverage and margin are estimates.
4. Execute Trade requests confirmation and creates a local record only. Edit
   records through the table's ⚙ cell, row double-click or Enter. Final P&L is manual.

No exchange/API account or Codex invocation is required. Optional chart/watchlist
discovery needs the existing TradingView Desktop debug/CDP connection plus Node.js
and TradingView MCP. Refresh is read-only. If unavailable, manual/fallback symbols
still work. The model selector does not run AI. All Charts is disabled in V1.

Exchange API inputs are UI-only. Enable Live Trading only toggles those fields;
values are cleared and never saved/transmitted. Do not enter real secrets. V1
does not place live/demo orders, synchronize balances or generate AI reports.

## Data and backup

Database: `%LOCALAPPDATA%\TradeWithAM\RiskManagementTradeJournalAgent\journal.sqlite3`.
The path is independent of the EXE directory and PyInstaller's runtime folder.
Close the app, copy the entire user-data folder to a private backup, and preserve
it when upgrading. Do not publish database/WAL/SHM files or replace real data with
a sample database. Trade history/capital snapshots survive exchange edits/deletion.

## Source and customization

Follow [README](README.md) for relative environment/build commands and sizing
assumptions. Start the full [ChatGPT Master Prompt](docs/CHATGPT_MASTER_PROMPT.md)
for one-step-at-a-time setup or optional future features. It never asks for real
API secrets and keeps demo integration as separate, explicitly approved development.
