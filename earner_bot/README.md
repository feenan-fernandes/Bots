# Ouroboros (Earner Bot) v3.1

Ouroboros is a high-frequency, fully autonomous cryptocurrency trading bot designed specifically for Binance Spot Markets. It leverages a multi-engine architecture to dynamically adapt to live market regimes, ensuring capital preservation and mathematical edge.

## Quick Start Guide

### 1. Installation
Ensure you have Python 3.9+ installed.
Install the required dependencies:
`ash
pip install -r requirements.txt
`

### 2. Configuration
1. Rename the provided .env.example file to .env.
2. Open the .env file and insert your Binance API credentials:
   - BINANCE_API_KEY
   - BINANCE_SECRET
*(Note: Ensure your Binance API key has Spot Trading permissions enabled. IP whitelisting is highly recommended for security).*

### 3. Launching the Bot
Simply run the included batch file to start the server and open the local UI:
`ash
Ouroboros_Manager.bat
`
Alternatively, you can run the Python server directly:
`ash
python app.py
`
The dashboard will be available in your browser at http://127.0.0.1:5000.

### 4. The Dashboard
When you open the UI, you will be prompted for a passphrase. The default passphrase is **Ouroboros**.

From the dashboard, you can:
- Toggle **Paper Mode** (Simulated trading) ON or OFF.
- View live active trades and recent trade history.
- Monitor the bot's live evaluation of the top 20 crypto assets.
- See the current market regime (TRENDING, RANGING, NOISE) determined by the bot.

## Safety Mechanisms
- **Paper Mode:** By default, Paper Mode is set to 	rue in your .env. We highly recommend letting the bot run in Paper Mode for 24-48 hours to ensure it is identifying setups correctly before switching to live capital.
- **Adaptive Kelly Engine:** The bot will never risk your entire portfolio on a single trade. It mathematically calculates the safest position size based on its trailing win rate.
- **Emergency Halt:** If the bot detects a Black Swan event (massive market-wide volatility), it will instantly halt all trading and cancel open orders.

## Support
Check the logs/ directory if you experience any connection issues with Binance.
