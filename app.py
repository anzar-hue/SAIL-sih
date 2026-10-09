import os
import json
from flask import app


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
def generate_gemini_briefing(cargo, price, lo, hi, constraint, wx):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

    prompt = f"""
You are the Director of Commercial Logistics at Steel Authority of India Limited (SAIL).
Generate a concise 2-paragraph executive decision briefing for the Board based on this data:
- Cargo: {cargo.upper()}
- Predicted Spot Price: ₹{price:,.2f}/tonne (Band: ₹{lo:,.2f} - ₹{hi:,.2f})
- Physical Handling Constraint: {constraint}
- Destination Port: {wx['port']} (Status: {wx['risk_level']}, Wind: {wx['wind_speed_knots']} kts, Delay: {wx['estimated_delay_days']} days)
- Demurrage Exposure: ₹{wx['demurrage_exposure_inr']:,.2f}

Format strictly as:
Paragraph 1: Procurement & Pricing Strategy (recommend buying tactics based on the band).
Paragraph 2: Tactical Logistics & Chemical Risk (synthesize weather with the physical handling constraint).
"""
    try:
        client = genai.Client(api_key=api_key)
        res = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return res.text
    except Exception as e:
        print(f"Gemini generation error: {e}")
        return None

# --- 4. API Endpoints ---
@app.route('/api/dashboard-data', methods=['GET'])
def get_dashboard_data():
    if not os.path.exists(JSON_PATH):
        return jsonify({"error": "sail_v2_summary.json not found"}), 404
    with open(JSON_PATH, 'r') as f:
        data = json.load(f)
    return jsonify(data)

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
    briefing = generate_gemini_briefing(selected_cargo, price, price - ci, price + ci, constraint, wx)
    if briefing:
        data['executive_briefing'] = briefing

    # 5. Persist to disk so terminal and other services remain in sync
    with open(JSON_PATH, 'w') as f:
        json.dump(data, f, indent=4)

    return jsonify(data)

if __name__ == '__main__':
    print("SAIL Flask Backend running on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)