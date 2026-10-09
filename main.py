import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.tree import DecisionTreeRegressor, plot_tree
from sklearn.preprocessing import StandardScaler
import matplotlib.pyplot as plt

# 1. Load the CSVs
coal_df = pd.read_csv('coal.csv')
fuel_df = pd.read_csv('rawfuel.csv')
port_df = pd.read_csv('economic_raw_port_cargo_volume_india (1).csv')
ex_df = pd.read_csv('exchange_rate_india.csv') 
vessel_df = pd.read_csv('vessels.csv')
freight_df = pd.read_csv("freight raw.csv")

# 2. Fix the Dates
coal_df['Date'] = pd.to_datetime(coal_df['financial_year'].astype(str).str[:4], format='%Y')
fuel_df['Date'] = pd.to_datetime(fuel_df['year'].astype(str) + '-' + fuel_df['month'], format='%Y-%b')
port_df['Date'] = pd.to_datetime(port_df['financial_year'].astype(str).str[:4], format='%Y')
ex_df['Date'] = pd.to_datetime(ex_df['year'].astype(str) + '-' + ex_df['month'], format='%Y-%b') # <-- Exchange Date


# 3. Filter to Australian Coking Coal
coal_df = coal_df[(coal_df['country'] == 'Australia') & (coal_df['coal_type'] == 'COKING')]

# 4. Extract ONLY the columns we need
port_coal = port_df[['Date', 'coal_000_tonnes']]
ex_subset = ex_df[['Date', 'usd_inr_monthly_average']]

vessel_coal = vessel_df[vessel_df['category'].str.contains('Panamax', case=False, na=False)].copy()

vessel_coal = vessel_df[vessel_df['category']== 'Panamax']
vessel_coal['dwt_mt'] = vessel_coal['dwt_mt'].str.replace(',', '').astype(float)
mean_dwt = vessel_coal['dwt_mt'].mean()
vessel_coal['fuel_consumptio_mt/day'] = pd.to_numeric(
 vessel_coal['fuel_consumptio_mt/day'].astype(str).str.replace(',', ''), 
 errors='coerce'
)
mean_fuel = vessel_coal['fuel_consumptio_mt/day'].mean()

import numpy as np
if np.isnan(mean_fuel):
   print("DEBUG: Fuel data missing from CSV. Using industry standard 35.0 MT/day.")
   mean_fuel = 35.0

print(f"DEBUG: Found {len(vessel_coal)} Panamax vessels.")
print(f"DEBUG: Average Capacity = {mean_dwt} MT")
print(f"DEBUG: Average Fuel Burn = {mean_fuel} MT/day")

# 5. Merge all datasets together
master_df = pd.merge(coal_df, fuel_df, on='Date', how='inner')
master_df = pd.merge(master_df, port_coal, on='Date', how='inner')
master_df = pd.merge(master_df, ex_subset, on='Date', how='inner') 
master_df['panamax_capacity'] = mean_dwt
master_df['Fuel_perday'] = mean_fuel
master_df['voyage_fuel_tons'] = master_df['Fuel_perday'] * 20



# Clean missing values

# --- FEATURE ENGINEERING: STANDARDIZE CURRENCY ---
# Multiply USD fuel price by the exchange rate to get INR fuel price
master_df['fuel_price_inr'] = master_df['bix_global_avg_usd_per_tonne'] * master_df['usd_inr_monthly_average']
master_df['consumption_perday'] = master_df['fuel_price_inr']*master_df['Fuel_perday']
master_df['total_voyage_cost'] = master_df['voyage_fuel_tons'] * master_df['fuel_price_inr']
master_df['freight_cost_per_tonne'] = master_df['total_voyage_cost'] / master_df['panamax_capacity']
master_df = master_df.dropna(subset=['price_inr_per_tonne', 'bix_global_avg_usd_per_tonne', 'coal_000_tonnes', 'usd_inr_monthly_average', 'consumption_perday'])
# 6. Define Features (X) and Target (y)

X = master_df[['fuel_price_inr', 'coal_000_tonnes']]
y = master_df['price_inr_per_tonne']


# 7. Chronological Split (Train: 2009-2014, Test: 2015-2016)
train_mask = master_df['Date'] < '2015-01-01'
test_mask = master_df['Date'] >= '2015-01-01'

X_train, X_test = X[train_mask], X[test_mask]
y_train, y_test = y[train_mask], y[test_mask]

tree_model = DecisionTreeRegressor(max_depth=3, random_state=42)
tree_model.fit(X_train, y_train)
# 8. Train and Predict
model = Ridge(alpha=1.0)
model.fit(X_train, y_train)
predictions = model.predict(X_test)

mae = mean_absolute_error(y_test, predictions)
r_value = master_df['freight_cost_per_tonne'].corr(master_df['price_inr_per_tonne'])
print(f"The 'r' value for Freight Cost vs Price is: {r_value:.2f}")
print("\n--- Correlation (r) with Coal Price ---")
# numeric_only=True prevents errors from text columns
print(master_df.corr(numeric_only=True)['price_inr_per_tonne'])
print(f"Final Economic Model Error (MAE): Off by ₹{mae:.2f} per tonne")
print(f"The predictions are {predictions}")

# --- VISUALIZING THE ECONOMIC MODEL ---

plt.figure(figsize=(15, 10))
plot_tree(
    tree_model,
    feature_names=X.columns.tolist(),
    filled=True,
    rounded=True,
    fontsize=10
)

plt.title("SAIL Economic Model: Decision Tree Flowchart")
plt.show()
plt.figure(figsize=(10, 6)) # Sets the window size

# Plot the actual vs predicted points
plt.scatter(y_test, predictions, color='blue', s=100, label='Model Guesses')

# Draw the "Perfect Prediction" red dashed line
min_val = min(y_test.min(), predictions.min())
max_val = max(y_test.max(), predictions.max())
plt.plot([min_val, max_val], [min_val, max_val], color='red', linestyle='--', linewidth=2, label='Perfect Accuracy')

# Add labels and title
plt.title('SAIL Economic Model: Actual vs Predicted Coal Prices')
plt.xlabel('Actual Historical Price (₹)')
plt.ylabel('Predicted Model Price (₹)')
plt.legend()
plt.grid(True, linestyle='--', alpha=0.7)

# Display the graph!
plt.show()