# Install Risk Management & Trade Journal Agent with ChatGPT

Use the existing [installation instructions](INSTALL.md), [README](README.md)
and [ChatGPT Master Prompt](docs/CHATGPT_MASTER_PROMPT.md) for this repository's
actual setup workflow.

1. Open [docs/CHATGPT_MASTER_PROMPT.md](docs/CHATGPT_MASTER_PROMPT.md) on GitHub.
2. Copy everything between **START OF PROMPT** and **END OF PROMPT**.
3. Start a new [ChatGPT conversation](https://chatgpt.com/) and paste that text.
4. Answer the first question about your operating system and whether you want
   the ready-made Windows EXE or the Python source.
5. Follow one instruction at a time and share the result before continuing.
   Ask ChatGPT to use [INSTALL.md](INSTALL.md), the [README](README.md) and the
   [official Windows release](https://github.com/tradewithamofficial/Risk-Management-Trade-Journal-Agent/releases/tag/v1.0.0)
   to verify each setup step. If an error occurs, resolve it before moving on.
6. Once installation works, choose whether to keep using V1 or discuss optional
   customization through the same master prompt.

The packaged Windows application includes Python; Python, PyCharm and Codex are
not required for risk calculations and local records. TradingView watchlist
discovery is optional and uses the existing TradingView Desktop/Node.js/MCP setup.
V1 records trades locally; it does not place exchange orders or run AI reports.

Follow [INSTALL.md's data and backup guidance](INSTALL.md#data-and-backup) before
upgrading or customizing. Keep your trade database and backups private, and never
paste API keys, passwords or authentication tokens into chat.
