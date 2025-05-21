import pandas as pd
import re

# Load the current CSV
csv_path = "backend/data/tickers.csv"
df = pd.read_csv(csv_path)

# Clean the name column: remove anything after the first ' - '
df["name"] = df["name"].apply(lambda x: re.split(r" - ", str(x))[0].strip())

# Save the cleaned file
df.to_csv(csv_path, index=False)

print(f"✅ Cleaned ticker names saved to {csv_path} ({len(df)} rows updated).")
