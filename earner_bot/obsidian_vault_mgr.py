"""
obsidian_vault_mgr.py — Automated Obsidian Knowledge Vault for Ouroboros Bot
Generates rich markdown notes, trade dossiers, mistake taxonomies, and daily journals
with bi-directional wikilinks for Obsidian's interactive Graph View.
"""
import os
import io
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

logger = logging.getLogger("Ouroboros.vault")

VAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Obsidian_Vault")
TRADES_DIR = os.path.join(VAULT_DIR, "Trades")
MISTAKES_DIR = os.path.join(VAULT_DIR, "Mistakes")
DAILY_DIR = os.path.join(VAULT_DIR, "Daily_Journals")
ORDERFLOW_DIR = os.path.join(VAULT_DIR, "Order_Flow")

class ObsidianVaultManager:
    def __init__(self, vault_path: str = VAULT_DIR):
        self.vault_path = vault_path
        self.trades_dir = os.path.join(self.vault_path, "Trades")
        self.mistakes_dir = os.path.join(self.vault_path, "Mistakes")
        self.daily_dir = os.path.join(self.vault_path, "Daily_Journals")
        self.orderflow_dir = os.path.join(self.vault_path, "Order_Flow")
        self._ensure_structure()

    def _ensure_structure(self):
        for d in [self.trades_dir, self.mistakes_dir, self.daily_dir, self.orderflow_dir]:
            os.makedirs(d, exist_ok=True)
            
        index_file = os.path.join(self.vault_path, "README.md")
        if not os.path.exists(index_file):
            content = """# 🧠 Ouroboros Trading Brain: Obsidian Memory Vault

Welcome to the automated external memory vault of the Ouroboros Quantitative Trading Engine.

## 🗺️ Vault Architecture
- **[[Trades/]]**: Full order flow dossiers, entry depth, exit execution, and microsecond telemetry for every trade.
- **[[Mistakes/]]**: Post-mortem failure taxonomy where the bot classifies losses and learns to suppress unprofitable patterns.
- **[[Daily_Journals/]]**: Chronological rollups of daily PnL, win rates, and market regime distributions.
- **[[Order_Flow/]]**: Microstructure snapshots (OFI, Bid/Ask Depth, CVD).

## 🕸️ How to View the Knowledge Graph
1. Open Obsidian Desktop.
2. Select **Open folder as vault** and choose this `Obsidian_Vault` folder.
3. Press `Ctrl + G` to open the **Interactive Graph View**.
4. Watch the neural web connect every trade to its market regime, currency pair, and mistake classifications!
"""
            with io.open(index_file, "w", encoding="utf-8") as f:
                f.write(content)

    def record_trade_entry(self, trade_id: str, trade_data: Dict[str, Any], orderflow: Optional[Dict[str, Any]] = None) -> str:
        """
        Creates a new trade dossier note when a position opens.
        Returns the absolute file path.
        """
        symbol = trade_data.get("symbol", "UNKNOWN")
        side = trade_data.get("side", "BUY")
        entry_price = float(trade_data.get("price", 0.0))
        qty = float(trade_data.get("qty", 0.0))
        regime = trade_data.get("regime", "UNKNOWN")
        stop_loss = float(trade_data.get("stop_loss", 0.0))
        take_profit = float(trade_data.get("take_profit", 0.0))
        atr = float(trade_data.get("atr", trade_data.get("atr_at_entry", 0.0)))
        entry_time = trade_data.get("entry_time", datetime.now(timezone.utc).isoformat())
        score = trade_data.get("score", 0)
        breakdown = trade_data.get("breakdown", {})

        date_str = entry_time.split("T")[0] if "T" in entry_time else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        safe_id = trade_id.replace(":", "_").replace("-", "_")
        filename = f"TRADE_{safe_id}_{symbol}.md"
        filepath = os.path.join(self.trades_dir, filename)

        of = orderflow or {}
        ofi = of.get("ofi", 0.0)
        spread_bps = of.get("spread_bps", 0.0)
        cvd_delta = of.get("cvd_delta", 0.0)
        lead_lag_lead = of.get("futures_lead_pct", 0.0)
        depth_bids = of.get("top_bids", [])
        depth_asks = of.get("top_asks", [])

        # Format Depth Table
        depth_table_rows = []
        max_rows = max(len(depth_bids), len(depth_asks), 1)
        for i in range(min(max_rows, 5)):
            b_p = f"${depth_bids[i][0]:.2f}" if i < len(depth_bids) else "-"
            b_q = f"{depth_bids[i][1]:.4f}" if i < len(depth_bids) else "-"
            a_p = f"${depth_asks[i][0]:.2f}" if i < len(depth_asks) else "-"
            a_q = f"{depth_asks[i][1]:.4f}" if i < len(depth_asks) else "-"
            depth_table_rows.append(f"| {b_q} | {b_p} | **Level {i+1}** | {a_p} | {a_q} |")
        depth_table_md = "\n".join(depth_table_rows) if depth_table_rows else "| - | - | Level 1 | - | - |"

        content = f"""---
type: trade
id: "{trade_id}"
symbol: "{symbol}"
side: "{side}"
status: "OPEN"
entry_price: {entry_price:.4f}
qty: {qty:.6f}
regime: "{regime}"
score: {score}
entry_time: "{entry_time}"
tags:
  - trade
  - {symbol}
  - {side}
  - regime/{regime}
  - status/OPEN
---

# 🚀 Trade Dossier: {symbol} ({side}) — `{trade_id}`

## 📌 Executive Summary
- **Asset**: [[{symbol}]]
- **Direction**: **{side}**
- **Entry Price**: `${entry_price:.4f}`
- **Position Size**: `{qty:.6f} {symbol.replace('USDT', '')}` (~`${qty * entry_price:.2f} USD`)
- **Market Regime**: [[Regime_{regime}]]
- **Confluence Score**: `{score}/100`
- **Execution Timestamp**: `{entry_time}`
- **Daily Journal**: [[Daily_{date_str}]]

---

## 🔬 Order Flow & Microstructure (Pre-Execution Snapshot)
The bot captured the following microsecond order book metrics directly prior to fill:

| Metric | Captured Value | Institutional Meaning |
| :--- | :--- | :--- |
| **Order Flow Imbalance (OFI)** | `{ofi:+.3f}` | Ratio of Bid vs Ask queue pressure (-1.0 to +1.0) |
| **Bid-Ask Spread** | `{spread_bps:.2f} bps` | Liquidity tightness at fill time |
| **CVD Delta (Flow)** | `{cvd_delta:+.2f}` | Taker market sweep aggression |
| **Futures Lead-Lag Delta** | `{lead_lag_lead:+.3f}%` | Price velocity lead on Binance Futures |

### Level-2 Order Book Queue at Entry
| Bid Qty | Bid Price | Depth Level | Ask Price | Ask Qty |
| :--- | :--- | :---: | :--- | :--- |
{depth_table_md}

---

## 🛡️ Risk & Protection Parameters
- **Stop Loss Target**: `${stop_loss:.4f}` (`{((stop_loss - entry_price)/entry_price*100):+.2f}%`)
- **Take Profit Target**: `${take_profit:.4f}` (`{((take_profit - entry_price)/entry_price*100):+.2f}%`)
- **ATR at Entry**: `${atr:.4f}`
- **Confluence Breakdown**:
```json
{json.dumps(breakdown, indent=2)}
```

---
*Status: Position active and monitored via real-time WebSocket tick engine.*
"""
        with io.open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
            
        self.update_daily_journal(date_str, f"[[Trades/{filename}|{symbol} ({side})]]", 0.0, 0.0, "OPEN")
        return filepath

    def record_trade_exit(self, trade_id: str, symbol: str, exit_data: Dict[str, Any], autopsy: Optional[Dict[str, Any]] = None) -> str:
        """
        Appends closing metrics, PnL, slippage, and post-mortem autopsy to the trade file.
        """
        safe_id = trade_id.replace(":", "_").replace("-", "_")
        filename = f"TRADE_{safe_id}_{symbol}.md"
        filepath = os.path.join(self.trades_dir, filename)

        exit_price = float(exit_data.get("exit_price", 0.0))
        entry_price = float(exit_data.get("entry_price", 0.0))
        pnl_pct = float(exit_data.get("pnl_pct", 0.0))
        pnl_usd = float(exit_data.get("pnl_usd", 0.0))
        pnl_aed = float(exit_data.get("pnl_aed", pnl_usd * 3.6725))
        trigger = exit_data.get("trigger", "MANUAL")
        exit_time = exit_data.get("exit_time", datetime.now(timezone.utc).isoformat())
        date_str = exit_time.split("T")[0] if "T" in exit_time else datetime.now(timezone.utc).strftime("%Y-%m-%d")

        is_win = pnl_usd > 0
        outcome_tag = "outcome/WIN" if is_win else "outcome/LOSS"

        ap = autopsy or {}
        mistake_id = ap.get("mistake_id")
        mistake_title = ap.get("mistake_title", "Unclassified")
        autopsy_notes = ap.get("notes", "No additional notes.")
        adaptation_action = ap.get("adaptation_action", "No penalty applied.")

        mistake_link = f"[[Mistakes/{mistake_id}|{mistake_title}]]" if mistake_id else "None (Profitable or Normal Market Variance)"

        # Read existing file or create if missing
        existing_content = ""
        if os.path.exists(filepath):
            with io.open(filepath, "r", encoding="utf-8") as f:
                existing_content = f.read()

        # Update Frontmatter
        if "status: \"OPEN\"" in existing_content:
            existing_content = existing_content.replace('status: "OPEN"', f'status: "CLOSED"\nexit_price: {exit_price:.4f}\npnl_pct: {pnl_pct:.2f}\npnl_usd: {pnl_usd:.2f}')
            existing_content = existing_content.replace("- status/OPEN", f"- status/CLOSED\n  - {outcome_tag}\n  - trigger/{trigger}")
            if mistake_id:
                existing_content = existing_content.replace(f"- {outcome_tag}", f"- {outcome_tag}\n  - mistake/{mistake_id}")

        exit_section = f"""

---

## 🏁 Trade Closure & Execution Telemetry
- **Exit Timestamp**: `{exit_time}`
- **Exit Trigger**: `{trigger}`
- **Exit Price**: `${exit_price:.4f}`
- **Net PnL %**: `{pnl_pct:+.2f}%`
- **Net PnL ($)**: `${pnl_usd:+.2f} USD`
- **Net PnL (AED)**: `{pnl_aed:+.2f} AED`
- **Outcome**: **{'🟢 WIN' if is_win else '🔴 LOSS'}**

---

## 🧠 Post-Mortem Autopsy & Machine Learning Adaptation
- **Diagnosed Failure Pattern**: {mistake_link}
- **Autopsy Findings**:
> {autopsy_notes}

- **Bot Adaptive Action**:
> `{adaptation_action}`

---
*Dossier archived into Ouroboros Neural Vault.*
"""
        final_content = (existing_content + exit_section) if existing_content else exit_section
        with io.open(filepath, "w", encoding="utf-8") as f:
            f.write(final_content)

        # Update Mistake File if there was a recognized failure
        if mistake_id:
            self.update_mistake_note(
                mistake_id=mistake_id,
                mistake_title=mistake_title,
                description=ap.get("description", "Identified failure pattern."),
                trade_link=f"[[Trades/{filename}|{symbol} ({trigger})]]",
                pnl_usd=pnl_usd
            )

        # Update Daily Journal
        self.update_daily_journal(date_str, f"[[Trades/{filename}|{symbol}]]", pnl_usd, pnl_pct, "CLOSED")
        return filepath

    def update_mistake_note(self, mistake_id: str, mistake_title: str, description: str, trade_link: str, pnl_usd: float):
        """Updates a living mistake note with links to all affected trades."""
        filename = f"{mistake_id}.md"
        filepath = os.path.join(self.mistakes_dir, filename)

        if not os.path.exists(filepath):
            content = f"""---
type: mistake_taxonomy
id: "{mistake_id}"
title: "{mistake_title}"
tags:
  - mistake
  - taxonomy
  - {mistake_id}
---

# ⚠️ Failure Taxonomy: {mistake_title} (`{mistake_id}`)

## 📖 Pattern Definition & Diagnostic Criteria
> {description}

## 📉 Cumulative Performance Impact
- **Total Incurred Losses**: `${abs(pnl_usd):.2f} USD`
- **Current Dynamic Penalty**: `-20 Confluence Score Points`

## 🔗 Affected Trade Dossiers
- {trade_link} (Lost: `${pnl_usd:.2f} USD`)
"""
        else:
            with io.open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            append_link = f"\n- {trade_link} (Lost: `${pnl_usd:.2f} USD`)"
            if trade_link not in content:
                content += append_link

        with io.open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    def update_daily_journal(self, date_str: str, trade_link: str, pnl_usd: float, pnl_pct: float, status: str):
        """Maintains the chronological daily performance journal."""
        filename = f"Daily_{date_str}.md"
        filepath = os.path.join(self.daily_dir, filename)

        if not os.path.exists(filepath):
            content = f"""---
type: daily_journal
date: "{date_str}"
tags:
  - daily_journal
  - journal/{date_str}
---

# 📅 Daily Trading Journal: {date_str}

## 📊 Performance Rollup
| Metric | Value |
| :--- | :--- |
| **Journal Date** | `{date_str}` |
| **Total Logged Activity** | Active |

## 📝 Trade Logs
| Trade Reference | Status | PnL (%) | PnL (USD) |
| :--- | :--- | :--- | :--- |
| {trade_link} | `{status}` | `{pnl_pct:+.2f}%` | `${pnl_usd:+.2f}` |
"""
        else:
            with io.open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            if trade_link not in content:
                row = f"\n| {trade_link} | `{status}` | `{pnl_pct:+.2f}%` | `${pnl_usd:+.2f}` |"
                content += row

        with io.open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

vault_mgr = ObsidianVaultManager()
