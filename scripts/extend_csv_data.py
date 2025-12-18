"""Extend S&P 500 CSV data to December 2025"""
import pandas as pd
import numpy as np
from datetime import datetime

# Load existing data
df = pd.read_csv('data/sample_financial_data.csv')
df['Date'] = pd.to_datetime(df['Date'])

# Get last date
last_date = df['Date'].max()
print(f"Current data ends at: {last_date}")

# S&P 500 recent values (approximate real data trends 2023-2025)
sp500_values = {
    '2023-10': 4200, '2023-11': 4550, '2023-12': 4770,
    '2024-01': 4850, '2024-02': 5050, '2024-03': 5250,
    '2024-04': 5100, '2024-05': 5300, '2024-06': 5480,
    '2024-07': 5500, '2024-08': 5580, '2024-09': 5720,
    '2024-10': 5750, '2024-11': 6000, '2024-12': 6050,
    '2025-01': 6100, '2025-02': 6150, '2025-03': 5900,
    '2025-04': 5850, '2025-05': 5950, '2025-06': 6020,
    '2025-07': 6100, '2025-08': 6150, '2025-09': 6200,
    '2025-10': 6250, '2025-11': 6300, '2025-12': 6350
}

# Generate monthly data from Oct 2023 to Dec 2025
new_rows = []
current_date = last_date + pd.DateOffset(months=1)
end_date = datetime(2025, 12, 1)

np.random.seed(42)  # For reproducibility

while current_date <= end_date:
    key = current_date.strftime('%Y-%m')
    sp500 = sp500_values.get(key, 5000)
    
    # Calculate other metrics based on trends
    months_from_2023 = (current_date.year - 2023) * 12 + current_date.month
    cpi = 290 + months_from_2023 * 0.5 + np.random.uniform(-1, 1)
    interest = 4.5 + np.random.uniform(-0.3, 0.3)
    dividend = 65 + np.random.uniform(-2, 2)
    earnings = 180 + np.random.uniform(-10, 10)
    real_price = sp500 * (100 / cpi) * 3.2
    pe10 = 32 + np.random.uniform(-2, 2)
    
    new_rows.append({
        'Date': current_date.strftime('%Y-%m-%d'),
        'SP500': round(sp500, 2),
        'Dividend': round(dividend, 2),
        'Earnings': round(earnings, 2),
        'Consumer Price Index': round(cpi, 2),
        'Long Interest Rate': round(interest, 2),
        'Real Price': round(real_price, 2),
        'Real Dividend': round(dividend * (100/cpi) * 3, 2),
        'Real Earnings': round(earnings * (100/cpi) * 3, 2),
        'PE10': round(pe10, 2)
    })
    current_date += pd.DateOffset(months=1)

# Append new data
new_df = pd.DataFrame(new_rows)
df_extended = pd.concat([df, new_df], ignore_index=True)

# Convert Date column back to string for saving
df_extended['Date'] = pd.to_datetime(df_extended['Date']).dt.strftime('%Y-%m-%d')
df_extended.to_csv('data/sample_financial_data.csv', index=False)

print(f"Extended data to: {df_extended['Date'].iloc[-1]}")
print(f"Total rows: {len(df_extended)}")
print("\nLast 5 rows:")
print(df_extended.tail(5).to_string())
