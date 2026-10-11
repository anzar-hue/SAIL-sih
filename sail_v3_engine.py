import pandas as pd
import numpy as np
from sklearn.linear_model import Ridge
import joblib
import os

USD_INR = 83.5  # port demurrage rates are quoted in USD/day

# ==========================================================
# CARGO-SPECIFIC EVENT SENSITIVITIES  (Layer 2 inputs)
# PLACEHOLDER VALUES chosen from domain reasoning, NOT fitted to data.
# When official SAIL / maritime datasets arrive, replace these two tables
# (or fill them from a regression) - no other code needs to change.
# Any cargo/event missing here falls back to the flat shock matrix below.
# ==========================================================
# Price multiplier applied to the predicted future base price
CARGO_SHOCK_MATRIX = {
    "coking_coal": {  # same values as the original flat matrix
        "war": 1.25, "port_closed": 1.15, "weather_issues": 1.10,
        "disaster": 1.20, "industry_needs_rise": 1.12,
    },
    "iron_ore": {  # liquefaction in rain -> weather hits hardest; less war-exposed
        "war": 1.12, "port_closed": 1.15, "weather_issues": 1.18,
        "disaster": 1.22, "industry_needs_rise": 1.15,
    },
    "fertilizer": {  # water-soluble + energy-linked -> weather and war both severe
        "war": 1.30, "port_closed": 1.12, "weather_issues": 1.20,
        "disaster": 1.25, "industry_needs_rise": 1.05,
    },
    "pol_liquid": {  # oil-driven -> war dominates; only high wind stops discharge
        "war": 1.35, "port_closed": 1.12, "weather_issues": 1.08,
        "disaster": 1.15, "industry_needs_rise": 1.06,
    },
}

# Expected berthing/discharge delay (days) in Scenario B per event
CARGO_WEATHER_DELAY_DAYS = {
    "coking_coal": {"weather_issues": 3, "disaster": 3},
    "iron_ore":    {"weather_issues": 5, "disaster": 6},
    "fertilizer":  {"weather_issues": 6, "disaster": 7},
    "pol_liquid":  {"weather_issues": 2, "disaster": 4},
}

def _cargo_key(name) -> str:
    """Maps UI/CLI cargo labels (e.g. 'Fertilizer (F&FRM)') to table keys."""
    n = str(name or "").lower()
    if "coal" in n: return "coking_coal"
    if "iron" in n: return "iron_ore"
    if "fert" in n: return "fertilizer"
    if "pol" in n: return "pol_liquid"
    return ""  # unknown cargo -> falls back to the flat shock matrix
    return None

class SAIL_V3_Operations_Engine:
    def __init__(self, data_path="data/coal_data.csv"):
        self.data_path = data_path
        self.base_model = Ridge(alpha=1.0)
        self.is_trained = False
        
        # Hardcoded Port Capacities (Layer 3 Limits)
        # In the future, this can be moved to a DB table
        self.port_limits = {
            "Paradip": {"max_capacity_tonnes": 150000, "demurrage_rate_per_day": 18000},
            "Haldia": {"max_capacity_tonnes": 80000, "demurrage_rate_per_day": 15000},
            "Vishakhapatnam": {"max_capacity_tonnes": 120000, "demurrage_rate_per_day": 16000}
        }
        
        # Vessel base freight costs (per tonne)
        self.vessel_rates = {
            "Panamax": 1200,
            "Capesize": 950, # Cheaper per tonne but requires bigger ports
            "Handymax": 1500
        }

    # ==========================================
    # LAYER 1: The Monthly Baseline (Math)
    # ==========================================
    def train_baseline_model(self, df):
        """Trains the underlying Ridge model on static historical data."""
        # Assuming df has 'bunker_fuel_price', 'import_volume', 'exchange_rate' -> 'target_price'
        features = ['bunker_fuel', 'import_volume', 'exchange_rate']
        
        # Fallback if columns don't perfectly match yet (keeps sprint moving)
        available_features = [col for col in features if col in df.columns]
        if not available_features:
            print("Warning: Missing core feature columns. Using dummy training for architecture test.")
            df['dummy_feature'] = np.random.rand(len(df))
            available_features = ['dummy_feature']
            
        X = df[available_features]
        y = df['price'] # Adjust target column name based on your CSV
        
        self.base_model.fit(X, y)
        self.is_trained = True
        joblib.dump(self.base_model, 'sail_v3_base_ridge.pkl')
        return "Layer 1 Baseline Trained Successfully."

    def predict_base_price(self, current_features):
        """Returns the static ML monthly prediction without shocks."""
        if not self.is_trained:
            # Load if exists, else return a fallback for testing
            if os.path.exists('sail_v3_base_ridge.pkl'):
                self.base_model = joblib.load('sail_v3_base_ridge.pkl')
                self.is_trained = True
            else:
                return 22500.0 # Fallback test price ₹22,500
        
        return self.base_model.predict(np.array([current_features]).reshape(1, -1))[0]

    # ==========================================
    # LAYER 2: The Dynamic Event Matrix (User Shocks)
    # ==========================================
    def apply_market_shock(self, base_price, event_keyword, cargo=None):
        """Applies probabilistic multipliers based on CFO event selections."""
        shock_matrix = {
            "none": 1.0,
            "war": 1.25,                  # +25% price spike
            "port_closed": 1.15,          # +15%
            "weather_issues": 1.10,       # +10%
            "disaster": 1.20,             # +20%
            "suspect_price_increase": 1.08,
            "suspect_price_decrease": 0.92,
            "festival": 1.05,
            "industry_needs_rise": 1.12   # India building new plants
        }
        
        event = event_keyword.lower()
        multiplier = CARGO_SHOCK_MATRIX.get(_cargo_key(cargo), {}).get(event, shock_matrix.get(event, 1.0))
        shock_price = base_price * multiplier
        return shock_price, multiplier

    # ==========================================
    # LAYER 3: Physical Logistics (Vessels & Ports)
    # ==========================================
    def calculate_logistics(self, tonnage, vessel_type, port_name, weather_risk_days):
        """Main constraints math: Calculates freight and forces demurrage penalties."""
        base_freight = self.vessel_rates.get(vessel_type, 1200) * tonnage
        
        port_data = self.port_limits.get(port_name, {"max_capacity_tonnes": 100000, "demurrage_rate_per_day": 15000})
        
        demurrage_penalty = 0
        days_delayed = weather_risk_days
        
        # Check port capacity breach
        if tonnage > port_data["max_capacity_tonnes"]:
            # Rule of thumb: every 10k tonnes over capacity adds 1 day of delay
            overage = tonnage - port_data["max_capacity_tonnes"]
            days_delayed += (overage / 10000)
            
        if days_delayed > 0:
            demurrage_penalty = days_delayed * port_data["demurrage_rate_per_day"] * USD_INR
            
        total_logistics_cost = base_freight + demurrage_penalty
        
        return {
            "base_freight_cost": base_freight,
            "demurrage_penalty": demurrage_penalty,
            "total_logistics_cost": total_logistics_cost,
            "days_delayed": days_delayed
        }

    # ==========================================
    # LAYER 4: The Procurement Optimizer (Profit Brain)
    # ==========================================
    def optimize_procurement(self, current_base, predicted_future_base, tonnage, vessel_type, port_name, event_keyword, target_months_away, godown_cost_per_tonne_per_month, cargo=None):
        """Compares Scenario A (Buy Now) vs Scenario B (Wait) and returns full matrices."""
        
        # SCENARIO A: Buy Now (No shocks, pay for godown storage)
        logistics_now = self.calculate_logistics(tonnage, vessel_type, port_name, weather_risk_days=0)
        cost_of_materials_now = current_base * tonnage
        storage_cost = godown_cost_per_tonne_per_month * tonnage * target_months_away
        
        total_scenario_a = cost_of_materials_now + logistics_now["total_logistics_cost"] + storage_cost
        
        # SCENARIO B: Wait until target month (Subject to shocks and weather risk)
        shock_price, multiplier = self.apply_market_shock(predicted_future_base, event_keyword, cargo)
        
        # Estimate weather risk days based on event
        default_delay = 3 if event_keyword in ["weather_issues", "disaster"] else 0
        expected_weather_delays = CARGO_WEATHER_DELAY_DAYS.get(_cargo_key(cargo), {}).get(event_keyword, default_delay)
        logistics_future = self.calculate_logistics(tonnage, vessel_type, port_name, expected_weather_delays)
        
        cost_of_materials_future = shock_price * tonnage
        total_scenario_b = cost_of_materials_future + logistics_future["total_logistics_cost"]
        
        # Calculate Variance (User expected vs ML baseline)
        user_variance_cost = total_scenario_b - (predicted_future_base * tonnage + logistics_future["base_freight_cost"])

        return {
            "scenario_a_buy_now": {
                "material_cost": cost_of_materials_now,
                "logistics": logistics_now,
                "godown_storage_cost": storage_cost,
                "total_cost": total_scenario_a
            },
            "scenario_b_wait": {
                "predicted_base_material_cost": predicted_future_base * tonnage,
                "shock_material_cost": cost_of_materials_future,
                "logistics": logistics_future,
                "total_cost": total_scenario_b
            },
            "financial_analysis": {
                "cheapest_option": "BUY_NOW" if total_scenario_a < total_scenario_b else "WAIT",
                "savings": abs(total_scenario_a - total_scenario_b),
                "user_expected_variance": user_variance_cost,
                "applied_shock_multiplier": multiplier,
                "expected_weather_delay_days": expected_weather_delays
            }
        }

# ==========================================
# TEST EXECUTION
# ==========================================
if __name__ == "__main__":
    print("Initializing SAIL V3 Engine...")
    engine = SAIL_V3_Operations_Engine()
    
    # Simulating the inputs from your Phase 2 Frontend Gateway
    test_result = engine.optimize_procurement(
        current_base=22000, 
        predicted_future_base=21500, 
        tonnage=130000, 
        vessel_type="Panamax", 
        port_name="Vishakhapatnam", 
        event_keyword="industry_needs_rise", 
        target_months_away=3, 
        godown_cost_per_tonne_per_month=150
    )
    
    import json
    print("\n--- CFO Optimizer Output ---")
    print(json.dumps(test_result, indent=4))