with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.read().split('\n')

# Keep up to line 520 (index 520)
truncated = lines[:521]

# Append the main block
truncated.append('')
truncated.append('if __name__ == "__main__":')
truncated.append('    ws_engine.start()')
truncated.append('    app.run(host="0.0.0.0", port=8080, debug=False)')

with open('app.py', 'w', encoding='utf-8') as f:
    f.write('\n'.join(truncated))
