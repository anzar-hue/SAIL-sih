import pandas as pd
from sklearn.preprocessing import PolynomialFeatures
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error
import matplotlib.pyplot as plt

# 1. Load and Clean
port_df = pd.read_csv('economic_raw_port_cargo_volume_india (1).csv')
port_df['Date'] = pd.to_datetime(port_df['financial_year'].astype(str).str[:4], format='%Y')

# We need a strict numerical year for the math to work, not just a Date object
port_df['Year'] = port_df['Date'].dt.year 

# Drop what we don't need
port_df = port_df.drop(columns=['financial_year', 'total_cargo_000_tonnes'])

# 2. Melt to Long Format
long_port = port_df.melt(id_vars=['Date', 'Year'], var_name='Cargo_Type', value_name='Volume')
long_port['Cargo_Type'] = long_port['Cargo_Type'].str.replace('_000_tonnes', '')

coal_df = long_port[long_port['Cargo_Type'] == 'coal'].copy()
# 2. Define X and y directly
X = coal_df[['Year']]
y = coal_df['Volume']

# 3. Train/Test Split
train_mask = coal_df['Year'] <= 2018
test_mask = coal_df['Year'] > 2018

X_train, X_test = X[train_mask], X[test_mask]
y_train, y_test = y[train_mask], y[test_mask]

poly = PolynomialFeatures(degree=2)
X_train_poly = poly.fit_transform(X_train)
X_test_poly = poly.transform(X_test)

# We use standard Linear Regression, but feed it the curved data!
model = LinearRegression()
model.fit(X_train_poly, y_train)
predictions = model.predict(X_test_poly)

mae = mean_absolute_error(y_test, predictions)
print(f"Polynomial Predictor MAE: Off by {mae:.2f} thousand tonnes")
print(f"The predictions are {predictions}")
future_data = pd.DataFrame({'Year': [2026]})

# Transform the future data into a curve before predicting
future_poly = poly.transform(future_data)
future_pred = model.predict(future_poly)
print(f"\nPREDICTION: In 2026, India will handle {future_pred[0]:.2f} thousand tonnes of Coal.")

# --- VISUALIZING THE CURVE (COAL) ---
plt.figure(figsize=(10, 6))

# We already isolated coal_df at the top of the script, so we use it directly
plt.scatter(coal_df['Year'], coal_df['Volume'], color='black', s=50, label='Actual Coal Volume')

# Transform the exact same Year column to draw the red prediction line
coal_features_poly = poly.transform(coal_df[['Year']])
coal_predictions = model.predict(coal_features_poly)

plt.plot(coal_df['Year'], coal_predictions, color='red', linewidth=3, label='Polynomial Curve (Coal)')

plt.title('India Port Coal Volume: Exponential Growth Curve')
plt.xlabel('Year')
plt.ylabel('Cargo Volume (000 Tonnes)')
plt.legend()
plt.grid(True, linestyle='--', alpha=0.7)
plt.show()