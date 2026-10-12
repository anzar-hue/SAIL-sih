import os
import json
from datetime import date, timedelta
from flask import app
from local_memo import local_cfo_memo
import sqlite3
import base64
import io
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from google import genai
from flask import Flask, request, jsonify
from sail_v3_engine import SAIL_V3_Operations_Engine
from setup_history import setup_history_table
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIST = os.path.join(BASE_DIR, 'frontend', 'dist')
JSON_PATH = os.path.join(BASE_DIR, 'sail_v2_summary.json')
DB_PATH = os.path.join(BASE_DIR, 'sail_database.db')

# Point Flask's static and template routes to the built Vite dist folder
app = Flask(__name__, static_folder=FRONTEND_DIST, static_url_path='')
CORS(app)

# Serve the React App index page
@app.route('/')
def serve_index():
    if os.path.exists(os.path.join(FRONTEND_DIST, 'index.html')):
        return send_from_directory(FRONTEND_DIST, 'index.html')
    return "Frontend build not found. Please run 'npm run build' inside the frontend folder.", 404

# Serve any static JS/CSS assets
@app.route('/<path:path>')
def serve_static(path):
    if os.path.exists(os.path.join(FRONTEND_DIST, path)):
        return send_from_directory(FRONTEND_DIST, path)
    return send_from_directory(FRONTEND_DIST, 'index.html')
# Enable CORS so your React frontend running on port 5173 can query Flask on port 5000
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(BASE_DIR, 'sail_v2_summary.json')
DB_PATH = os.path.join(BASE_DIR, 'sail_database.db')

# --- 1. Maritime Weather Risk Engine ---
class WeatherRiskEngine:
    def __init__(self, db_path):
        self.db_path = db_path
        self.port_registry = {
            'mumbai': 'Mumbai', 'chennai': 'Chennai', 'colombo': 'Colombo',
            'dubai': 'Dubai', 'singapore': 'Singapore', 'rotterdam': 'Rotterdam'
        }
        self.port_coords = {
            'Mumbai': (18.9388, 72.8354), 'Chennai': (13.0827, 80.2707),
            'Colombo': (6.9271, 79.8612), 'Dubai': (25.2769, 55.2962),
            'Singapore': (1.3521, 103.8198), 'Rotterdam': (51.9225, 4.4791)
        }

    def calculate_demurrage_risk(self, port_name):
        daily_panamax_usd = 18000.0
        usd_inr = 83.50
        target_port = self.port_registry.get(str(port_name).lower()) or str(port_name) or "Mumbai"

        wind_speed = 0.0
        precipitation = 0.0
        extreme_flag = False
        data_source = "LIVE_API"

        # Online data attempt
        try:
            coords = self.port_coords.get(target_port, (18.9388, 72.8354))
            lat: float = coords[0]
            lon: float = coords[1]
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=precipitation,wind_speed_10m&wind_speed_unit=knots&timezone=auto"
            res = requests.get(url, timeout=3)
            res.raise_for_status()
            current = res.json()['current']
            wind_speed = current['wind_speed_10m']
            precipitation = current['precipitation']
            if wind_speed > 40.0:
                extreme_flag = True
        except Exception:
            # Offline database fallback
            data_source = "OFFLINE_DB"
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                query = "SELECT wind_speed_knots, significant_wave_height_m, extreme_event_flag FROM weather_observations WHERE location_name LIKE ? ORDER BY timestamp_utc DESC LIMIT 1"
                cursor.execute(query, (f'%{target_port}%',))
                row = cursor.fetchone()
                conn.close()
                if row:
                    wind_speed = row[0]
                    precipitation = row[1] * 10
                    extreme_flag = bool(row[2])
            except Exception:
                pass

        delay_days = 0
        risk_level = 'LOW / CLEAR BERTHING'
        if extreme_flag:
            delay_days = 6.0
            risk_level = 'CRITICAL / PORT CLOSURE'
        elif wind_speed > 30.0 or precipitation > 10.0:
            delay_days = 3.5
            risk_level = 'MODERATE / DISCHARGE DELAY'
        elif wind_speed > 20.0 or precipitation > 2.0:
            delay_days = 1.0
            risk_level = 'ELEVATED / MONITORING'

        demurrage_cost = delay_days * daily_panamax_usd * usd_inr
        return {
            'port': target_port,
            'data_source': data_source,
            'wind_speed_knots': round(wind_speed, 1),
            'risk_level': risk_level,
            'estimated_delay_days': delay_days,
            'demurrage_exposure_inr': round(demurrage_cost, 2)
        }

weather_engine = WeatherRiskEngine(DB_PATH)

# --- 2. Matplotlib Base64 Graph Generator ---
def render_trajectory_graph(cargo_key, base_price, ci, weather_status):
    historical_years = [2021, 2022, 2023, 2024, 2025]
    historical_prices = [
        base_price * 0.82, base_price * 0.90, base_price * 0.88, base_price * 0.95, base_price
    ]
    forecast_year = 2026

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(historical_years, historical_prices, marker='o', color='#084298', linewidth=2.5, label='Historical Market Trend')
    ax.plot([historical_years[-1], forecast_year], [historical_prices[-1], base_price],
            marker='X', color='#f97316', linestyle='--', linewidth=2, markersize=8, label='V2 Ridge Forecast')
    ax.fill_between([historical_years[-1], forecast_year],
                    [historical_prices[-1], base_price - ci],
                    [historical_prices[-1], base_price + ci],
                    color='#f97316', alpha=0.18, label='95% Confidence Band')

    weather_desc = f"{weather_status.get('risk_level', 'NORMAL')} ({weather_status.get('port', '')})"
    ax.set_title(f"SAIL Intelligence: {cargo_key.upper()} Price Trajectory\nLogistics Status: {weather_desc}",
                 fontsize=11, fontweight='bold', pad=10)
    ax.set_ylabel("INR / Tonne", fontsize=10)
    ax.grid(True, linestyle='--', alpha=0.5)
    ax.legend(loc='upper left', fontsize=9)

    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=140)
    plt.close(fig)
    buffer.seek(0)
    encoded = base64.b64encode(buffer.read()).decode('utf-8')
    return f"data:image/png;base64,{encoded}"

# --- 3. Gemini Executive Briefing Generator ---
_memo_cache = {}

def generate_v3_cfo_memo(optimization_data):
    api_key = os.environ.get("GEMINI_API_KEY")
    cache_key = json.dumps(optimization_data, sort_keys=True, default=str)
    if cache_key in _memo_cache:
        return _memo_cache[cache_key]
    if not api_key: return local_cfo_memo(optimization_data)

    prompt = f"""
You are an elite Supply Chain Risk Analyst for SAIL (Steel Authority of India).
I am providing you with an Operations Research cost matrix comparing a 'Buy Now' vs 'Wait' scenario.

DATA MATRIX:
{json.dumps(optimization_data, indent=2)}

INSTRUCTIONS:
Strictly act as a financial advisor. Output your response STRICTLY as clean, valid HTML using only <h3>, <p>, <ul>, <li>, and <strong> tags. Do NOT wrap the response in markdown code blocks (e.g. no ```html). Do NOT include an intro or closing remarks. Output EXACTLY these 4 sections:

<h3>1. THE VERDICT & TIMELINE</h3>
<p>State a definitive procurement recommendation. <strong>CRITICAL LIABILITY SHIELD:</strong> You MUST specify a strategic purchasing WINDOW (e.g., "Optimal procurement window: Weeks 2-4 of Month 2"). NEVER specify a single exact calendar day.</p>

<h3>2. MARGIN ANALYSIS & MITIGATION</h3>
<p>Explicitly calculate and state the exact Profit/Loss margin (as a % and absolute ₹ value) generated by choosing the optimal scenario over the alternative. If the overall market is highly shocked, provide a 1-sentence mitigation strategy.</p>

<h3>3. THE MATH JUSTIFICATION</h3>
<p>Detail the Godown Storage Cost versus the anticipated Demurrage Penalty and Market Shock variance to substantiate the margin analysis.</p>

<h3>4. ALTERNATIVE RISK</h3>
<p>State the specific financial exposure if the anticipated market event or weather disruption is 20% more severe than calculated.</p>
"""
    try:
        client = genai.Client(api_key=api_key)
        res = client.models.generate_content(model="gemini-3.8-flash", contents=prompt)
        text = (res.text or "").strip()
        if text.startswith("```"):
            text = text.strip("`").removeprefix("html").strip()
        _memo_cache[cache_key] = text
        return text
    except Exception as e:
        print(f"Gemini unavailable: {e}")
        return local_cfo_memo(optimization_data)

@app.route('/api/simulate', methods=['POST'])
def simulate():
    req = request.get_json() or {}
    selected_cargo = req.get('cargo', 'coking_coal')
    selected_port = req.get('port', 'Mumbai')

    if not os.path.exists(JSON_PATH):
        return jsonify({"error": "sail_v2_summary.json not found"}), 404

    with open(JSON_PATH, 'r') as f:
        data = json.load(f)

    # 1. Update maritime weather risk
    wx = weather_engine.calculate_demurrage_risk(selected_port)
    data['weather_risk_status'] = wx
    data['active_frontend_cargo'] = selected_cargo

    # 2. Extract cargo stats
    cargo_meta = data['models_diagnostics'].get(selected_cargo, {})
    price = cargo_meta.get('latest_predictions', [8000.0])[0]
    ci = cargo_meta.get('confidence_interval_half_width', 1000.0)
    constraint = cargo_meta.get('handling_constraint', '')

    # 3. Generate graph and embed
    data['active_graph_base64'] = render_trajectory_graph(selected_cargo, price, ci, wx)

    # 4. Generate AI briefing
    briefing = generate_v3_cfo_memo({
        "cargo": selected_cargo,
        "price": price,
        "lower_bound": price - ci,
        "upper_bound": price + ci,
        "constraint": constraint,
        "weather_status": wx
    })
    if briefing:
        data['executive_briefing'] = briefing

    # 5. Persist to disk so terminal and other services remain in sync
    with open(JSON_PATH, 'w') as f:
        json.dump(data, f, indent=4)

    return jsonify(data)


# Initialize the new V3 Engine globally
v3_engine = SAIL_V3_Operations_Engine()
setup_history_table(DB_PATH)  # creates / upgrades prediction_history

# Reference base prices per cargo (current, predicted future) in INR/tonne
CARGO_BASE_PRICES = {
    'Coking Coal': (22000.0, 21500.0),
    'Iron Ore': (8000.0, 7800.0),
    'Fertilizer (F&FRM)': (45000.0, 46000.0),
    'POL (Liquid)': (65000.0, 67000.0),
}

@app.route('/api/v3/origins', methods=['GET'])
def v3_origins():
    return jsonify(v3_engine.origins_by_cargo_label())

@app.route('/api/v3/optimize', methods=['POST'])
def optimize_v3():
    try:
        data = request.get_json(silent=True) or {}

        tonnage = float(data.get('tonnage', 100000))
        vessel_type = data.get('vessel_type', 'Panamax')
        port_name = data.get('port_name', 'Haldia')
        event_keyword = data.get('event_keyword', 'none')
        target_months_away = int(data.get('target_months_away', 0))
        godown_cost = float(data.get('godown_cost_per_tonne_per_month', 150))
        cargo = data.get('cargo', 'Coking Coal')
        if tonnage <= 0 or target_months_away < 0 or godown_cost < 0:
            raise ValueError('tonnage must be positive; months and storage cost cannot be negative')

        current_base, predicted_future_base = CARGO_BASE_PRICES.get(cargo, CARGO_BASE_PRICES['Coking Coal'])

        if data.get('delivery_date'):
            # Origin + date aware path
            today = date.fromisoformat(data.get('current_date') or date.today().isoformat())
            delivery = date.fromisoformat(data['delivery_date'])
            if not 0 < (delivery - today).days <= 365:
                raise ValueError('delivery_date must be 1 to 365 days after current_date')
            origin = data.get('origin') or v3_engine.default_origin(cargo)
            if origin not in v3_engine.origins_for(cargo):
                raise ValueError(f"'{origin}' is not a supported origin for {cargo}")
            # Bias correction learned from the user's recorded purchases (1.0 until 3+ exist)
            # Extra charges the user supplies (percent of the predicted cost); 0 = not provided
            extras_in = data.get('extras') or {}
            extras = {}
            for k in ('origin_tax_pct', 'india_tax_pct', 'sea_route_pct', 'other_pct', 'insurance_pct'):
                v = float(extras_in.get(k) or 0)
                if not 0 <= v <= 100:
                    raise ValueError(f'{k} must be between 0 and 100')
                extras[k] = v
            extras['incoterm'] = str(extras_in.get('incoterm', 'FOB')).upper()
            if extras['incoterm'] not in ('FOB', 'CIF'):
                raise ValueError('incoterm must be FOB or CIF')
            cal_factor, cal_n = _calibration(cargo)
            current_base *= cal_factor
            predicted_future_base *= cal_factor
            result = v3_engine.optimize_with_dates(
                cargo=cargo, origin=origin, tonnage=tonnage, vessel_type=vessel_type,
                port_name=port_name, event_keyword=event_keyword,
                current_base=current_base, predicted_future_base=predicted_future_base,
                godown_cost_per_tonne_per_month=godown_cost,
                current_date=today, delivery_date=delivery, extras=extras
            )
            result['calibration'] = {"factor": round(cal_factor, 3), "n": cal_n}
            result['history_id'] = _save_prediction(result, cargo, port_name, tonnage, event_keyword, today, delivery, cal_factor)
        else:
            # Legacy months-based path
            result = v3_engine.optimize_procurement(
                current_base=current_base,
                predicted_future_base=predicted_future_base,
                tonnage=tonnage,
                vessel_type=vessel_type,
                port_name=port_name,
                event_keyword=event_keyword,
                target_months_away=target_months_away,
                godown_cost_per_tonne_per_month=godown_cost,
                cargo=cargo
            )
        result['cargo_type'] = cargo
        result['port'] = port_name
        result['event_keyword'] = event_keyword

        # Keep the per-date table out of the memo so the AI advises a window, never an exact day
        memo_data = dict(result)
        if 'timing' in memo_data:
            memo_data['timing'] = {k: v for k, v in memo_data['timing'].items() if k not in ('candidates', 'suggested_date')}
        memo = generate_v3_cfo_memo(memo_data)
        return jsonify({
            "status": "success",
            "data": result,
            "executive_memo": memo
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400
# ==========================================
# PREDICTION HISTORY (closed loop: predict -> buy -> record actual -> calibrate)
# ==========================================
HISTORY_COLS = ("id, created_at, order_date, delivery_date, cargo_type, origin, port, tonnage, event_keyword, "
                "predicted_cost_per_tonne, predicted_landed_per_tonne, window_start, window_end, suggested_date, "
                "notify_after, actual_cost_per_tonne, variance_percent, status, notify_dismissed, calibration_factor, "
                "origin_tax_pct, india_tax_pct, sea_route_pct, other_pct, insurance_pct, incoterm, extras_total_pct, "
                "predicted_extras_per_tonne, actual_port_labour, actual_docking, actual_anchoring, actual_cleaning, "
                "actual_other_charges, actual_extra_charges_total, incident_cost, realized_risks")

def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _calibration(cargo):
    """Average actual/raw-predicted ratio over the last 10 recorded purchases of this cargo, clipped to 0.8-1.2."""
    try:
        conn = _db()
        rows = conn.execute(
            "SELECT predicted_cost_per_tonne AS p, actual_cost_per_tonne AS a, COALESCE(calibration_factor, 1.0) AS cf "
            "FROM prediction_history WHERE cargo_type = ? AND status = 'COMPLETED' "
            "AND predicted_cost_per_tonne > 0 AND actual_cost_per_tonne > 0 ORDER BY id DESC LIMIT 10", (cargo,)).fetchall()
        conn.close()
    except Exception:
        return 1.0, 0
    if len(rows) < 3:
        return 1.0, len(rows)
    # the stored prediction already contains the factor used at the time, so undo it to get the raw ratio
    factor = sum(r['a'] * r['cf'] / r['p'] for r in rows) / len(rows)
    return min(max(factor, 0.8), 1.2), len(rows)

def _save_prediction(result, cargo, port, tonnage, event, today, delivery, cal_factor):
    """Logs a feasible recommendation. Re-running identical inputs updates the pending row instead of adding a new one."""
    try:
        timing = result['timing']
        if not timing['feasible']:
            return None
        best = min(timing['candidates'], key=lambda c: c['total_cost'])
        notify_after = (date.fromisoformat(timing['suggested_date']) + timedelta(days=7)).isoformat()
        ex, sm = result['extras'], result['scenario_matrix']
        vals = (best['material_cost'] / tonnage, best['total_cost'] / tonnage, timing['order_window']['start'],
                timing['order_window']['end'], timing['suggested_date'], notify_after, cal_factor,
                ex['origin_tax_pct'], ex['india_tax_pct'], ex['sea_route_pct'], ex['other_pct'], ex['insurance_pct'],
                ex['incoterm'], sm['extras_pct'], sm['extras_amount'] / tonnage)
        conn = _db()
        key = (cargo, result['origin'], port, tonnage, event, today.isoformat(), delivery.isoformat())
        row = conn.execute("SELECT id FROM prediction_history WHERE status = 'PENDING' AND cargo_type = ? AND origin = ? "
                           "AND port = ? AND tonnage = ? AND event_keyword = ? AND order_date = ? AND delivery_date = ?", key).fetchone()
        if row:
            conn.execute("UPDATE prediction_history SET predicted_cost_per_tonne = ?, predicted_landed_per_tonne = ?, window_start = ?, "
                         "window_end = ?, suggested_date = ?, notify_after = ?, calibration_factor = ?, origin_tax_pct = ?, india_tax_pct = ?, "
                         "sea_route_pct = ?, other_pct = ?, insurance_pct = ?, incoterm = ?, extras_total_pct = ?, "
                         "predicted_extras_per_tonne = ? WHERE id = ?", vals + (row['id'],))
            pid = row['id']
        else:
            cur = conn.execute("INSERT INTO prediction_history (cargo_type, origin, port, tonnage, event_keyword, order_date, delivery_date, "
                               "predicted_cost_per_tonne, predicted_landed_per_tonne, window_start, window_end, suggested_date, notify_after, "
                               "calibration_factor, origin_tax_pct, india_tax_pct, sea_route_pct, other_pct, insurance_pct, incoterm, "
                               "extras_total_pct, predicted_extras_per_tonne, created_at, status, notify_dismissed) "
                               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), 'PENDING', 0)",
                               key + vals)
            pid = cur.lastrowid
        conn.commit()
        conn.close()
        return pid
    except Exception:
        return None

def _history_stats(rows):
    done = [r for r in rows if r['status'] == 'COMPLETED' and r['actual_cost_per_tonne'] and r['predicted_cost_per_tonne']]
    if not done:
        return {"n": 0}
    err = [r['actual_cost_per_tonne'] - r['predicted_cost_per_tonne'] for r in done]
    charged = [r['actual_extra_charges_total'] / r['tonnage'] for r in done if r.get('tonnage') and r.get('actual_extra_charges_total')]
    return {
        "n": len(done),
        "mae": sum(abs(x) for x in err) / len(done),
        "mape": sum(abs(x) / r['actual_cost_per_tonne'] * 100 for x, r in zip(err, done)) / len(done),
        "bias": sum(x / r['predicted_cost_per_tonne'] * 100 for x, r in zip(err, done)) / len(done),
        "incidents": sum(1 for r in done if r.get('realized_risks')),
        "avg_extra_charges_per_tonne": sum(charged) / len(charged) if charged else 0,
    }

@app.route('/api/v3/history', methods=['GET'])
def history_list():
    conn = _db()
    rows = [dict(r) for r in conn.execute(f"SELECT {HISTORY_COLS} FROM prediction_history ORDER BY id DESC LIMIT 200")]
    conn.close()
    return jsonify({"rows": rows, "stats": _history_stats(rows)})

@app.route('/api/v3/history/due', methods=['GET'])
def history_due():
    try:
        as_of = date.fromisoformat(request.args.get('as_of') or date.today().isoformat())
    except ValueError:
        return jsonify({"status": "error", "message": "as_of must be YYYY-MM-DD"}), 400
    conn = _db()
    rows = [dict(r) for r in conn.execute(
        f"SELECT {HISTORY_COLS} FROM prediction_history WHERE status = 'PENDING' AND COALESCE(notify_dismissed, 0) = 0 "
        "AND notify_after IS NOT NULL AND notify_after <= ? ORDER BY notify_after", (as_of.isoformat(),))]
    conn.close()
    return jsonify(rows)

@app.route('/api/v3/history/<int:pid>/dismiss', methods=['POST'])
def history_dismiss(pid):
    conn = _db()
    conn.execute("UPDATE prediction_history SET notify_dismissed = 1 WHERE id = ?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

RISK_CODES = {"CYCLONE_WEATHER", "CARGO_DAMAGE_LOSS", "FINE_PENALTY", "WAR_ROUTE_DISRUPTION", "SHIP_LOSS",
              "LABOUR_STRIKE", "CUSTOMS_HOLD"}
CHARGE_FIELDS = ("port_labour", "docking", "anchoring", "cleaning", "other_charges")

@app.route('/api/v3/history/<int:pid>/actual', methods=['POST'])
def history_actual(pid):
    """Records what really happened: purchase price, port charges actually paid, and incidents on the way."""
    body = request.get_json(silent=True) or {}
    try:
        actual = float(body.get('actual_price') or 0)
        charges = {k: float(body.get(k) or 0) for k in CHARGE_FIELDS}
        incident_cost = float(body.get('incident_cost') or 0)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "All amounts must be numbers"}), 400
    risks = body.get('risks') or []
    if not isinstance(risks, list) or any(r not in RISK_CODES for r in risks):
        return jsonify({"status": "error", "message": "Unknown incident type"}), 400
    if not 0 < actual <= 10_000_000 or any(not 0 <= v <= 1e11 for v in [*charges.values(), incident_cost]):
        return jsonify({"status": "error", "message": "An amount is out of range"}), 400
    conn = _db()
    row = conn.execute("SELECT predicted_cost_per_tonne AS p FROM prediction_history WHERE id = ?", (pid,)).fetchone()
    if not row or not row['p']:
        conn.close()
        return jsonify({"status": "error", "message": "prediction not found"}), 404
    variance = (actual - row['p']) / row['p'] * 100
    if abs(variance) > 50 and not body.get('confirm'):
        conn.close()
        return jsonify({"status": "needs_confirmation",
                        "message": f"That is {variance:+.0f}% away from the prediction. Save it anyway?"}), 409
    conn.execute("UPDATE prediction_history SET actual_cost_per_tonne = ?, variance_percent = ?, actual_port_labour = ?, actual_docking = ?, "
                 "actual_anchoring = ?, actual_cleaning = ?, actual_other_charges = ?, actual_extra_charges_total = ?, incident_cost = ?, "
                 "realized_risks = ?, status = 'COMPLETED', notify_dismissed = 1 WHERE id = ?",
                 (actual, variance, charges['port_labour'], charges['docking'], charges['anchoring'], charges['cleaning'],
                  charges['other_charges'], sum(charges.values()), incident_cost, ",".join(risks), pid))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "variance_percent": variance})

if __name__ == '__main__':
    print("SAIL Flask Backend running on http://localhost:5000")
    app.run(host='127.0.0.1', port=5000, debug=False)