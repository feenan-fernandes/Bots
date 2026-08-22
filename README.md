# Trading Bots Repository

Welcome to my centralized repository for algorithmic trading bots and quantitative financial tools.

## Included Bots

### 1. Ouroboros (Earner Bot) - v3.1
**Location:** /earner_bot

Ouroboros is a fully autonomous cryptocurrency trading engine built in Python. It is designed to execute strictly in Spot markets with an architecture that dynamically shifts its aggression based on live market regimes.

**Key Architecture:**
- **Macro Swing Strategy:** Hunts for structural breakouts using VWAP Z-Score standard deviations combined with CVD (Cumulative Volume Delta) alignment.
- **Adaptive Kelly Engine:** Mathematically guarantees long-term survival by dynamically sizing positions based on the bot's live win rate over the trailing 10 trades.
- **Dynamic Thresholding:** Automatically scales the strictness of entry requirements (Confluence Score & Z-Score) up or down depending on whether the market is currently rewarding or rejecting the edge.
- **Multi-Timeframe Gate (MTF):** Filters out trades that contradict the macro trend on the 1H timeframe.
- **Kalman Filter:** Smooths price action to detect the true underlying trend through the noise.

**Setup Instructions:**
1. Clone the repository.
2. Navigate to /earner_bot.
3. Create a .env file containing your BINANCE_API_KEY, BINANCE_SECRET, and TELEGRAM_BOT_TOKEN.
4. Run Ouroboros_Manager.bat to launch the Flask server and local UI dashboard.

---
*Disclaimer: The code provided in this repository is for educational and research purposes. Algorithmic trading carries significant financial risk.*
