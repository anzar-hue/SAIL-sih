import pandas as pd
import numpy as np
from sklearn.linear_model import Ridge
import joblib
import os
import copy
import math
import sqlite3
from datetime import timedelta

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

# ==========================================================
# ORIGINS (where the cargo is imported from) - hardcoded per cargo
# Coking-coal PRICE FACTORS and SUPPLY VOLUMES are recomputed at start-up from
# real import records in sail_database.db (last 3 financial years). Every other
# number below (freight, transit, weather delay, FX drift) is a PLACEHOLDER
# ESTIMATE pending official SAIL / maritime data.
#   price_factor       price vs. the reference price (1.0 = reference)
#   freight_inr        sea/rail freight, INR per tonne (excl. bunker fuel)
#   transit_days       sailing time to the East Coast ports
#   weather_delay_days expected loading-port weather delay
#   fx_factor          exchange-rate drift of the supplier currency vs. USD
# ==========================================================
CARGO_LABELS = {
    "coking_coal": "Coking Coal", "iron_ore": "Iron Ore",
    "fertilizer": "Fertilizer (F&FRM)", "pol_liquid": "POL (Liquid)",
}
ORIGIN_DATA = {
    "coking_coal": {
        "Australia":  {"price_factor": 1.00, "freight_inr": 1800, "transit_days": 20, "weather_delay_days": 1.0, "fx_factor": 1.01, "currency": "AUD"},
        "USA":        {"price_factor": 0.98, "freight_inr": 2800, "transit_days": 40, "weather_delay_days": 0.5, "fx_factor": 1.00, "currency": "USD"},
        "Canada":     {"price_factor": 1.03, "freight_inr": 2300, "transit_days": 32, "weather_delay_days": 0.5, "fx_factor": 0.99, "currency": "CAD"},
        "Mozambique": {"price_factor": 0.83, "freight_inr": 1300, "transit_days": 14, "weather_delay_days": 1.5, "fx_factor": 1.00, "currency": "USD"},
        "Russia":     {"price_factor": 0.67, "freight_inr": 1700, "transit_days": 22, "weather_delay_days": 1.5, "fx_factor": 1.00, "currency": "RUB",
                       "note": "Sanctions / compliance review required"},
    },
    "iron_ore": {
        "Domestic (Odisha)": {"price_factor": 0.90, "freight_inr": 600,  "transit_days": 4,  "weather_delay_days": 1.0, "fx_factor": 1.00, "currency": "INR"},
        "Australia":         {"price_factor": 1.00, "freight_inr": 1800, "transit_days": 20, "weather_delay_days": 1.0, "fx_factor": 1.01, "currency": "AUD"},
        "South Africa":      {"price_factor": 1.05, "freight_inr": 2100, "transit_days": 20, "weather_delay_days": 0.5, "fx_factor": 0.98, "currency": "ZAR"},
        "Brazil":            {"price_factor": 1.10, "freight_inr": 3200, "transit_days": 38, "weather_delay_days": 0.5, "fx_factor": 0.97, "currency": "BRL"},
    },
    "fertilizer": {
        "Saudi Arabia": {"price_factor": 0.97, "freight_inr": 1500, "transit_days": 9,  "weather_delay_days": 0.5, "fx_factor": 1.00, "currency": "SAR"},
        "Jordan":       {"price_factor": 0.99, "freight_inr": 1700, "transit_days": 10, "weather_delay_days": 0.5, "fx_factor": 1.00, "currency": "USD"},
        "Morocco":      {"price_factor": 1.00, "freight_inr": 2400, "transit_days": 22, "weather_delay_days": 0.5, "fx_factor": 1.00, "currency": "USD"},
        "Russia":       {"price_factor": 0.92, "freight_inr": 2200, "transit_days": 25, "weather_delay_days": 1.5, "fx_factor": 1.00, "currency": "RUB",
                         "note": "Sanctions / compliance review required"},
    },
    "pol_liquid": {
        "Saudi Arabia": {"price_factor": 1.00, "freight_inr": 900,  "transit_days": 9,  "weather_delay_days": 0.5, "fx_factor": 1.00, "currency": "SAR"},
        "UAE":          {"price_factor": 1.01, "freight_inr": 850,  "transit_days": 8,  "weather_delay_days": 0.5, "fx_factor": 1.00, "currency": "AED"},
        "Iraq":         {"price_factor": 0.97, "freight_inr": 1000, "transit_days": 11, "weather_delay_days": 1.0, "fx_factor": 1.00, "currency": "USD"},
        "USA":          {"price_factor": 1.04, "freight_inr": 2600, "transit_days": 38, "weather_delay_days": 1.0, "fx_factor": 1.00, "currency": "USD"},
    },
}
DB_COUNTRY_NAMES = {"USA": "United States Of America"}
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sail_database.db")

# Bunker fuel: vessel burn x transit days x price. PLACEHOLDER price - the BIX
# series stored in sail_database.db ends in 2016, so replace with a fresh feed.
BUNKER_USD_PER_MT = 600.0
VESSEL_BURN_MT_PER_DAY = 35.0
PANAMAX_DWT = 75205

# Layer 5 - port disbursements per vessel call: towing, pilotage, anchoring, cleaning,
# broker and port maintenance dues. PLACEHOLDER: the History tab records the real amounts.
PORT_CALL_USD = 50000.0

# Layer 6 - statutory / route charges entered by the user as % of the model's predicted cost
EXTRA_PCT_KEYS = ("origin_tax_pct", "india_tax_pct", "sea_route_pct", "other_pct")
EXTRA_LABELS = {
    "origin_tax_pct": "Import-origin taxes",
    "india_tax_pct": "Indian taxes (customs duty, IGST and levies)",
    "sea_route_pct": "Sea-route charges (canal tolls, war-risk and piracy surcharges)",
    "other_pct": "Other charges (agency and broker fees, penalties, tariffs)",
    "insurance_pct": "Marine insurance (FOB purchases)",
}

def _db_coking_coal_origins(db_path):
    """Real coking-coal import volume (Mt) and avg price (INR/t) by origin, last 3 FYs."""
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT country, SUM(quantity_million_tonnes), SUM(amount_inr_crore) FROM coking_coal "
            "WHERE coal_type = 'COKING' AND financial_year IN "
            "(SELECT DISTINCT financial_year FROM coking_coal ORDER BY 1 DESC LIMIT 3) GROUP BY country"
        ).fetchall()
        conn.close()
    except Exception:
        return {}
    return {c: {"mt": q, "price": a * 1e7 / (q * 1e6)} for c, q, a in rows if q and q > 0}
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
    # ORIGINS + DATE-BASED ORDER TIMING
    # ==========================================
    def _get_origins(self):
        cached = getattr(self, "_origins_cache", None)
        if cached is not None:
            return cached
        origins = copy.deepcopy(ORIGIN_DATA)
        db = _db_coking_coal_origins(DB_PATH)
        base = db.get("Australia", {}).get("price")
        for name, o in origins["coking_coal"].items():
            rec = db.get(DB_COUNTRY_NAMES.get(name, name))
            if rec:
                o["supply_mt_3fy"] = round(rec["mt"], 2)
                if base:
                    o["price_factor"] = round(rec["price"] / base, 3)
        self._origins_cache = origins
        return origins

    def origins_by_cargo_label(self):
        return {CARGO_LABELS[k]: list(v.keys()) for k, v in self._get_origins().items()}

    def origins_for(self, cargo):
        return list(self._get_origins().get(_cargo_key(cargo), {}).keys())

    def default_origin(self, cargo):
        names = self.origins_for(cargo)
        return names[0] if names else ""

    def plan_order(self, cargo, origin, tonnage, vessel_type, port_name, event_keyword,
                   current_base, predicted_future_base, godown_cost, current_date, delivery_date, extras=None):
        """Costs every candidate order date (weekly) for one origin and picks the cheapest."""
        key = _cargo_key(cargo)
        o = self._get_origins()[key][origin]
        extras = extras or {}
        incoterm = str(extras.get("incoterm", "FOB")).upper()
        pct_items = {k: float(extras.get(k) or 0) for k in EXTRA_PCT_KEYS}
        pct_items["insurance_pct"] = float(extras.get("insurance_pct") or 0) if incoterm == "FOB" else 0.0
        extras_pct = sum(pct_items.values())
        # Layer 5: one port call per Panamax load; none for a domestic (rail) origin
        port_disb = 0.0 if o.get("currency") == "INR" else max(math.ceil(tonnage / PANAMAX_DWT), 1) * PORT_CALL_USD * USD_INR
        shock_mult = self.apply_market_shock(predicted_future_base, event_keyword, cargo)[1]
        default_delay = 3 if event_keyword in ["weather_issues", "disaster"] else 0
        event_delay = CARGO_WEATHER_DELAY_DAYS.get(key, {}).get(event_keyword, default_delay)
        lead_days = math.ceil(o["transit_days"] + o["weather_delay_days"] + event_delay)
        horizon = max((delivery_date - current_date).days, 1)
        latest_offset = horizon - lead_days
        feasible = latest_offset >= 0
        last = max(latest_offset, 0)
        offsets = list(range(0, last + 1, 7))
        if offsets[-1] != last:
            offsets.append(last)
        bunker_per_tonne = VESSEL_BURN_MT_PER_DAY * o["transit_days"] * BUNKER_USD_PER_MT * USD_INR / PANAMAX_DWT

        def cost_at(off, with_event, full_shock=False):
            t = off / horizon  # price path: linear from today's price to the predicted price at delivery
            price = (current_base + (predicted_future_base - current_base) * t) * o["price_factor"] * o["fx_factor"]
            mult = (shock_mult if full_shock else 1 + (shock_mult - 1) * t) if with_event else 1.0  # shock builds toward delivery
            wx_days = o["weather_delay_days"] + (event_delay if with_event else 0)
            log = self.calculate_logistics(tonnage, vessel_type, port_name, wx_days)
            freight = (o["freight_inr"] + bunker_per_tonne) * tonnage
            storage_days = max(horizon - (off + o["transit_days"] + wx_days), 0)
            storage = godown_cost * tonnage * storage_days / 30
            material = price * mult * tonnage
            return {"material": material, "material_base": price * tonnage, "freight": freight,
                    "demurrage": log["demurrage_penalty"], "days_delayed": log["days_delayed"],
                    "storage": storage, "port_disb": port_disb,
                    "total": material + freight + log["demurrage_penalty"] + storage + port_disb}

        candidates = []
        for off in offsets:
            w, n = cost_at(off, True), cost_at(off, False)
            ex = n["total"] * extras_pct / 100.0  # extra charges: % of the no-disruption predicted cost
            candidates.append({
                "date": (current_date + timedelta(days=off)).isoformat(), "offset_days": off,
                "material_cost": w["material"], "material_cost_no_event": n["material"],
                "freight_cost": w["freight"], "demurrage_penalty": w["demurrage"],
                "days_delayed": w["days_delayed"], "storage_cost": w["storage"],
                "total_cost": w["total"], "total_cost_no_event": n["total"],
                "port_disbursements": w["port_disb"], "extras_amount": ex,
                "total_cost_extras": n["total"] + ex, "total_cost_all": w["total"] + ex,
            })
        best = min(candidates, key=lambda c: c["total_cost"])  # earliest date wins ties
        best_date = current_date + timedelta(days=best["offset_days"])
        # Stress test at the recommended date: the disruption applies in full, plus any extra charges
        bn, bw = cost_at(best["offset_days"], False), cost_at(best["offset_days"], True, True)
        bex = bn["total"] * extras_pct / 100.0
        stress = {"no_disruption": bn["total"], "normal_risk": bw["total"],
                  "extras_only": bn["total"] + bex, "combined": bw["total"] + bex, "extras_amount": bex}
        return {
            "origin": origin, "feasible": feasible, "lead_days": lead_days,
            "transit_days": o["transit_days"], "weather_delay_days": o["weather_delay_days"],
            "event_delay_days": event_delay, "shock_multiplier": shock_mult,
            "latest_order_date": (current_date + timedelta(days=latest_offset)).isoformat() if feasible else None,
            "earliest_arrival": (current_date + timedelta(days=lead_days)).isoformat(),
            "order_window": {
                "start": max(best_date - timedelta(days=3), current_date).isoformat(),
                "end": min(best_date + timedelta(days=3), current_date + timedelta(days=last)).isoformat(),
            },
            "candidates": candidates, "best": best, "best_total": best["total_cost"],
            "landed_cost_per_tonne": best["total_cost"] / tonnage,
            "supply_mt_3fy": o.get("supply_mt_3fy"), "note": o.get("note"),
            "price_factor": o["price_factor"], "freight_inr": o["freight_inr"],
            "extras_pct": extras_pct, "extras_items": pct_items, "incoterm": incoterm, "stress": stress,
        }

    def optimize_with_dates(self, cargo, origin, tonnage, vessel_type, port_name, event_keyword,
                            current_base, predicted_future_base, godown_cost_per_tonne_per_month,
                            current_date, delivery_date, extras=None):
        """Origin + date aware optimizer. Returns the same keys as optimize_procurement, plus timing and origin intelligence."""
        def plan(name):
            return self.plan_order(cargo, name, tonnage, vessel_type, port_name, event_keyword, current_base,
                                   predicted_future_base, godown_cost_per_tonne_per_month, current_date, delivery_date, extras)

        plans = {name: plan(name) for name in self.origins_for(cargo)}
        sel = plans[origin]
        feasible_plans = [p for p in plans.values() if p["feasible"]]
        unflagged = [p for p in feasible_plans if not p["note"]]
        pool = unflagged or feasible_plans or list(plans.values())
        rec = min(pool, key=lambda p: p["best_total"] if feasible_plans else p["lead_days"])
        ranked = sorted(unflagged or feasible_plans, key=lambda p: p["best_total"])

        # --- reasons: generated from the numbers, not by the LLM ---
        crore = lambda x: f"Rs {x / 1e7:.2f} crore"
        reasons = []
        if not sel["feasible"]:
            reasons.append(f"{origin} needs about {sel['lead_days']} days to arrive, more than the time left before delivery.")
        if rec["origin"] != origin:
            if sel["feasible"] and sel["best_total"] > rec["best_total"]:
                reasons.append(f"{rec['origin']} lands {crore(sel['best_total'] - rec['best_total'])} cheaper than {origin} for {tonnage:,.0f} t "
                               f"(Rs {rec['landed_cost_per_tonne']:,.0f}/t vs Rs {sel['landed_cost_per_tonne']:,.0f}/t).")
            if rec["transit_days"] < sel["transit_days"]:
                reasons.append(f"Transit is {sel['transit_days'] - rec['transit_days']} days shorter ({rec['transit_days']} vs {sel['transit_days']} days).")
            if rec["price_factor"] < sel["price_factor"]:
                reasons.append(f"Material price is {(1 - rec['price_factor'] / sel['price_factor']) * 100:.0f}% lower.")
            if rec["weather_delay_days"] < sel["weather_delay_days"]:
                reasons.append("Lower expected loading-port weather delay.")
            if rec["supply_mt_3fy"] and sel["supply_mt_3fy"]:
                reasons.append(f"{rec['origin']} supplied {rec['supply_mt_3fy']:.1f} Mt vs {sel['supply_mt_3fy']:.1f} Mt from {origin} over the last 3 financial years.")
        elif not feasible_plans:
            reasons.append(f"{origin} is the fastest of all origins, but even it cannot arrive before the delivery date.")
        else:
            reasons.append(f"{origin} has the lowest landed cost among {len(ranked)} feasible origins (Rs {sel['landed_cost_per_tonne']:,.0f}/t).")
            if len(ranked) > 1:
                nxt = ranked[1]
                reasons.append(f"Next best is {nxt['origin']}, {crore(nxt['best_total'] - sel['best_total'])} more expensive.")
            if sel["supply_mt_3fy"]:
                reasons.append(f"{origin} supplied {sel['supply_mt_3fy']:.1f} Mt over the last 3 financial years, per SAIL import records.")
        for fc in sorted(feasible_plans, key=lambda p: p["best_total"]):
            if fc["note"] and fc["origin"] != rec["origin"] and fc["best_total"] < rec["best_total"]:
                reasons.insert(min(1, len(reasons)), f"{fc['origin']} is {crore(rec['best_total'] - fc['best_total'])} cheaper still but flagged: {fc['note']}.")
                break
        reasons = reasons[:4]

        comparison = [{
            "origin": p["origin"], "feasible": p["feasible"], "transit_days": p["transit_days"],
            "landed_cost_per_tonne": p["landed_cost_per_tonne"], "total_cost": p["best_total"],
            "supply_mt_3fy": p["supply_mt_3fy"], "note": p["note"], "order_window": p["order_window"],
        } for p in plans.values()]

        # --- map the date plan onto the Buy Now (A) vs Wait (B) structure the UI expects ---
        cands = sel["candidates"]
        A, B, best = cands[0], cands[-1], sel["best"]
        logi = lambda c: {"base_freight_cost": c["freight_cost"], "demurrage_penalty": c["demurrage_penalty"],
                          "port_disbursements": c["port_disbursements"],
                          "total_logistics_cost": c["freight_cost"] + c["demurrage_penalty"] + c["port_disbursements"], "days_delayed": c["days_delayed"]}
        alt = B if best["offset_days"] == 0 else A
        savings = alt["total_cost"] - best["total_cost"]
        # --- four-way scenario matrix at the recommended order date ---
        stress = sel["stress"]
        base_t = stress["no_disruption"]
        scenario_matrix = {
            "provided": sel["extras_pct"] > 0, "incoterm": sel["incoterm"], "extras_pct": sel["extras_pct"],
            "extras_amount": stress["extras_amount"],
            "extras_items_amount": {k: base_t * v / 100.0 for k, v in sel["extras_items"].items()},
            "totals": {k: stress[k] for k in ("no_disruption", "normal_risk", "extras_only", "combined")},
        }
        scenario_matrix["per_tonne"] = {k: v / tonnage for k, v in scenario_matrix["totals"].items()}
        missing = [EXTRA_LABELS[k] for k, v in sel["extras_items"].items()
                   if v == 0 and not (k == "insurance_pct" and sel["incoterm"] == "CIF")]
        timing = {k: sel[k] for k in ("feasible", "lead_days", "transit_days", "event_delay_days", "latest_order_date",
                                      "earliest_arrival", "order_window", "candidates")}
        timing["weather_delay_days_at_origin"] = sel["weather_delay_days"]
        timing["suggested_date"] = best["date"]
        return {
            "scenario_a_buy_now": {"material_cost": A["material_cost"], "logistics": logi(A),
                                   "godown_storage_cost": A["storage_cost"], "total_cost": A["total_cost"]},
            "scenario_b_wait": {"predicted_base_material_cost": B["material_cost_no_event"], "shock_material_cost": B["material_cost"],
                                "logistics": logi(B), "godown_storage_cost": B["storage_cost"], "total_cost": B["total_cost"]},
            "financial_analysis": {
                "cheapest_option": "BUY_NOW" if best["offset_days"] == 0 else "WAIT",
                "savings": savings,
                "margin_percent": (savings / alt["total_cost"] * 100) if alt["total_cost"] else 0.0,
                "user_expected_variance": B["material_cost"] - B["material_cost_no_event"],
                "applied_shock_multiplier": sel["shock_multiplier"],
                "expected_weather_delay_days": sel["event_delay_days"],
            },
            "origin": origin, "recommended_origin": rec["origin"], "origin_reasons": reasons,
            "origin_comparison": comparison, "timing": timing,
            "scenario_matrix": scenario_matrix, "inputs_not_provided": missing,
            "extras": {**sel["extras_items"], "incoterm": sel["incoterm"]},
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