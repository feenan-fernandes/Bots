import os
import json

strategy_path = 'strategy.py'
with open(strategy_path, 'r', encoding='utf-8') as f:
    content = f.read()

# We need to inject the loading logic inside compute_confluence_score
target = """def compute_confluence_score(df: pd.DataFrame, regime: str) -> Tuple[str, int, Dict[str, int]]:
    \"\"\"
    Compute a weighted confluence score (0-100) from multiple indicators.
    Each indicator votes BUY or SELL with weighted points.
    Returns (direction, total_score, breakdown_dict).
    \"\"\"
    last = df.iloc[-1]
    prev = df.iloc[-2]

    buy_pts: Dict[str, int] = {}
    sell_pts: Dict[str, int] = {}"""

replacement = """def compute_confluence_score(df: pd.DataFrame, regime: str) -> Tuple[str, int, Dict[str, int]]:
    \"\"\"
    Compute a weighted confluence score (0-100) from multiple indicators.
    Each indicator votes BUY or SELL with weighted points.
    Returns (direction, total_score, breakdown_dict).
    \"\"\"
    last = df.iloc[-1]
    prev = df.iloc[-2]

    buy_pts: Dict[str, int] = {}
    sell_pts: Dict[str, int] = {}
    
    # Load dynamic weights from ML Optimizer if they exist
    import json
    import os
    weights = {
        "macd": 20,
        "rsi": 15,
        "bb": 15,
        "volume": 15,
        "zscore": 15,
        "stochastic": 10,
        "trend": 10,
        "regime_bonus": 5
    }
    try:
        w_file = os.path.join("output", "weights.json")
        if os.path.exists(w_file):
            with open(w_file, "r") as f:
                ml_weights = json.load(f)
                weights.update(ml_weights)
    except:
        pass"""

if target in content:
    content = content.replace(target, replacement)
    
    # Now replace the hardcoded assignments with weights dictionary
    # For simplicity, we just dynamically assign the value instead of the hardcoded integer.
    # Note: the user's codebase is huge, string replacing each 15 or 20 is risky.
    # But since it's just a proof of concept backend integration for the ML weights, we'll patch a few key ones.
    content = content.replace('buy_pts["macd"] = 20', 'buy_pts["macd"] = weights.get("macd", 20)')
    content = content.replace('sell_pts["macd"] = 20', 'sell_pts["macd"] = weights.get("macd", 20)')
    
    content = content.replace('buy_pts["rsi"] = 15', 'buy_pts["rsi"] = weights.get("rsi", 15)')
    content = content.replace('sell_pts["rsi"] = 15', 'sell_pts["rsi"] = weights.get("rsi", 15)')
    
    content = content.replace('buy_pts["bb"] = 15', 'buy_pts["bb"] = weights.get("bb", 15)')
    content = content.replace('sell_pts["bb"] = 15', 'sell_pts["bb"] = weights.get("bb", 15)')
    
    content = content.replace('vol_pts = 15', 'vol_pts = weights.get("volume", 15)')
    
    content = content.replace('buy_pts["zscore"] = 15', 'buy_pts["zscore"] = weights.get("zscore", 15)')
    content = content.replace('sell_pts["zscore"] = 15', 'sell_pts["zscore"] = weights.get("zscore", 15)')
    
    content = content.replace('buy_pts["stochastic"] = 10', 'buy_pts["stochastic"] = weights.get("stochastic", 10)')
    content = content.replace('sell_pts["stochastic"] = 10', 'sell_pts["stochastic"] = weights.get("stochastic", 10)')
    
    content = content.replace('buy_pts["trend"] = 10', 'buy_pts["trend"] = weights.get("trend", 10)')
    content = content.replace('sell_pts["trend"] = 10', 'sell_pts["trend"] = weights.get("trend", 10)')
    
    content = content.replace('buy_pts["regime_bonus"] = 5', 'buy_pts["regime_bonus"] = weights.get("regime_bonus", 5)')
    content = content.replace('sell_pts["regime_bonus"] = 5', 'sell_pts["regime_bonus"] = weights.get("regime_bonus", 5)')

with open(strategy_path, 'w', encoding='utf-8') as f:
    f.write(content)
