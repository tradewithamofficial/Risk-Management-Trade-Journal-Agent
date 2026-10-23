# v1.0.0 — Risk Management & Trade Journal Agent

Initial Windows x64 release: dark CustomTkinter UI, static-capital exchange labels,
Decimal position sizing, LONG/SHORT validation, 0.1%–9.9% risk, >=5% warnings,
estimated leverage/margin, persistent local active/completed records and editing.

The final viewer-facing [ChatGPT Master Prompt](CHATGPT_MASTER_PROMPT.md) is
included in source and the Windows ZIP. The final gold robot icon is used unchanged.

Execute Trade records locally only. Exchange API fields are presentation-only;
credentials are not stored/transmitted. No exchange orders, balance synchronization,
AI reports or complete journal pages. Optional watchlist discovery remains read-only.

No saved personal database or credentials are distributed. Back up user data while
the application is closed and preserve it when upgrading. Python is bundled in
the Windows onedir ZIP; optional external chart/model tools are not bundled.
