with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.read().split('\n')

i = lines.index('if __name__ == "__main__":')

eps = """
@app.route("/api/ml/train", methods=["POST"])
@login_required
def ml_train():
    try:
        from ml_optimizer import ml_engine
        ml_engine.start_training()
        return jsonify({"status": "success", "message": "Training started"})
    except Exception as e:
        logger.error(f"ML train error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/ml/status")
@login_required
def ml_status():
    try:
        from ml_optimizer import ml_engine
        return jsonify({"status": "success", "data": ml_engine.get_status()})
    except Exception as e:
        logger.error(f"ML status error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
"""

new_content = '\n'.join(lines[:i]) + eps + '\n'.join(lines[i:])
with open('app.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
