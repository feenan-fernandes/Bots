---
type: trade
id: "test_run_001"
symbol: "BTCUSDT"
side: "BUY"
status: "CLOSED"
exit_price: 67200.0000
pnl_pct: -1.37
pnl_usd: -80.00
entry_price: 68000.0000
qty: 0.100000
regime: "TRENDING"
score: 85
entry_time: "2026-10-16T20:54:07.856115+00:00"
tags:
  - trade
  - BTCUSDT
  - BUY
  - regime/TRENDING
  - status/CLOSED
  - outcome/LOSS
  - mistake/Mistake_CVD_Exhaustion_Trap
  - trigger/STOP_LOSS
---

# 🚀 Trade Dossier: BTCUSDT (BUY) — `test_run_001`

## 📌 Executive Summary
- **Asset**: [[BTCUSDT]]
- **Direction**: **BUY**
- **Entry Price**: `$68000.0000`
- **Position Size**: `0.100000 BTC` (~`$6800.00 USD`)
- **Market Regime**: [[Regime_TRENDING]]
- **Confluence Score**: `85/100`
- **Execution Timestamp**: `2026-10-16T20:54:07.856115+00:00`
- **Daily Journal**: [[Daily_2026-10-16]]

---

## 🔬 Order Flow & Microstructure (Pre-Execution Snapshot)
The bot captured the following microsecond order book metrics directly prior to fill:

| Metric | Captured Value | Institutional Meaning |
| :--- | :--- | :--- |
| **Order Flow Imbalance (OFI)** | `-0.450` | Ratio of Bid vs Ask queue pressure (-1.0 to +1.0) |
| **Bid-Ask Spread** | `2.50 bps` | Liquidity tightness at fill time |
| **CVD Delta (Flow)** | `-12.50` | Taker market sweep aggression |
| **Futures Lead-Lag Delta** | `+0.000%` | Price velocity lead on Binance Futures |

### Level-2 Order Book Queue at Entry
| Bid Qty | Bid Price | Depth Level | Ask Price | Ask Qty |
| :--- | :--- | :---: | :--- | :--- |
| - | - | **Level 1** | - | - |

---

## 🛡️ Risk & Protection Parameters
- **Stop Loss Target**: `$0.0000` (`-100.00%`)
- **Take Profit Target**: `$0.0000` (`-100.00%`)
- **ATR at Entry**: `$0.0000`
- **Confluence Breakdown**:
```json
{
  "volatility_breakout": 50,
  "cvd_alignment": 30
}
```

---
*Status: Position active and monitored via real-time WebSocket tick engine.*


---

## 🏁 Trade Closure & Execution Telemetry
- **Exit Timestamp**: `2026-10-16T20:54:07.857114+00:00`
- **Exit Trigger**: `STOP_LOSS`
- **Exit Price**: `$67200.0000`
- **Net PnL %**: `-1.37%`
- **Net PnL ($)**: `$-80.00 USD`
- **Net PnL (AED)**: `-293.80 AED`
- **Outcome**: **🔴 LOSS**

---

## 🧠 Post-Mortem Autopsy & Machine Learning Adaptation
- **Diagnosed Failure Pattern**: [[Mistakes/Mistake_CVD_Exhaustion_Trap|CVD Exhaustion / Passive Absorption Trap]]
- **Autopsy Findings**:
> Buy signal was triggered while order book imbalance (OFI) was skewed negative. Aggressive sellers were in control despite price appearance.

- **Bot Adaptive Action**:
> `Penalty activated: Applying -20 score penalty to Mistake_CVD_Exhaustion_Trap patterns until win-rate re-establishes.`

---
*Dossier archived into Ouroboros Neural Vault.*
