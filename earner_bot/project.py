capital = 100000.0
monthly_roi = 0.0075 # 0.75% monthly (approx +6R in Spot)

print("| Month | Starting Balance | Net Monthly PnL | Ending Balance |")
print("|-------|------------------|-----------------|----------------|")
for month in range(1, 13):
    start = capital
    pnl = start * monthly_roi
    capital += pnl
    print(f"| Month {month:02d} | {start:,.2f} AED | +{pnl:,.2f} AED | {capital:,.2f} AED |")
