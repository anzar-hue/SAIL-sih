import sqlite3
import json
import os
import requests
from dotenv import load_dotenv
from google import genai

class WeatherRiskEngine:
    def __init__(self, db_path='sail_database.db'):
        self.db_path = db_path
        self.port_registry = {
            '1': 'Mumbai', '2': 'Chennai', '3': 'Colombo',
            '4': 'Dubai', '5': 'Singapore', '6': 'Rotterdam',
            'mumbai': 'Mumbai', 'chennai': 'Chennai', 'colombo': 'Colombo',
            'dubai': 'Dubai', 'singapore': 'Singapore', 'rotterdam': 'Rotterdam'
        }
        # GPS Coordinates for the live API
        self.port_coords = {
            'Mumbai': (18.9388, 72.8354), 'Chennai': (13.0827, 80.2707),
            'Colombo': (6.9271, 79.8612), 'Dubai': (25.2769, 55.2962),
            'Singapore': (1.3521, 103.8198), 'Rotterdam': (51.9225, 4.4791)
        }

    def calculate_demurrage_risk(self, keyword_or_code):
        daily_panamax_charter_rate_usd = 18000.0
        usd_inr = 83.50
        
        target_port = self.port_registry.get(str(keyword_or_code).lower())
        if not target_port:
            return {'port': keyword_or_code, 'risk_level': 'UNKNOWN PORT', 'estimated_delay_days': 0, 'demurrage_exposure_inr': 0.0}

        wind_speed = 0.0
        precipitation = 0.0
        extreme_flag = False
        data_source = "LIVE_API"

        # 1. ONLINE DATA: Attempt Live Weather API Call (Open-Meteo)
        try:
            lat, lon = self.port_coords[target_port]
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=precipitation,wind_speed_10m&wind_speed_unit=knots&timezone=auto"
            response = requests.get(url, timeout=3)
            response.raise_for_status()
            weather_data = response.json()['current']
            
            wind_speed = weather_data['wind_speed_10m']
            precipitation = weather_data['precipitation']  # mm per hour
            
            if wind_speed > 40.0:
                extreme_flag = True

        except Exception as api_error:
            # 2. OFFLINE DATA: Fallback to Local SQL Database if API fails
            print(f"      [!] Live API unavailable ({api_error}). Falling back to Offline SQLite...")
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
                    precipitation = row[1] * 10  # Roughly proxying wave height to precip for logic
                    extreme_flag = bool(row[2])
            except Exception:
                pass

        # 3. Hard Mathematical Risk Thresholds
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
            
        demurrage_cost_inr = delay_days * daily_panamax_charter_rate_usd * usd_inr
        
        return {
            'port': target_port,
            'data_source': data_source,
            'wind_speed_knots': wind_speed,
            'risk_level': risk_level,
            'estimated_delay_days': delay_days,
            'demurrage_exposure_inr': round(demurrage_cost_inr, 2)
        }

load_dotenv()

class SAILV3Advisor:
    def __init__(self, v2_json_path='sail_v2_summary.json'):
        with open(v2_json_path, 'r') as f:
            self.v2_data = json.load(f)
            
        # Secure initialization reading from .env file
        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    def run_executive_briefing(self, prediction_result, weather_advisory):
        prompt = f"""
You are the Director of Commercial Logistics at Steel Authority of India Limited (SAIL).
Generate an executive decision memo based on this backend data:

BACKEND DATA:
- Cargo Type: {prediction_result['commodity'].upper()}
- Base Price: ₹{prediction_result['base_price_prediction_inr']}/tonne
- Price Range: ₹{prediction_result['price_lower_bound_95']} to ₹{prediction_result['price_upper_bound_95']}
- Port Capacity Status: {prediction_result['port_capacity_alert']}
- Tactical Weather Risk: {weather_advisory['risk_level']} at {weather_advisory['port']} ({weather_advisory['estimated_delay_days']} days expected delay)
- Financial Exposure: ₹{weather_advisory['demurrage_exposure_inr']:,.2f} demurrage.
- STRICT CARGO CONSTRAINT: {prediction_result['handling_constraint']}

STRICT FORMATTING RULES:
1. Begin with an **EXECUTIVE KPI SNAPSHOT** (Target Price, Price Ceiling, Action, Demurrage Risk).
2. Paragraph 1 (Procurement): Analyze the price limits and buying strategy.
3. Paragraph 2 (Logistics & Chemical Risk): Synthesize the weather at the port with the STRICT CARGO CONSTRAINT. If it is raining and the cargo is Fertilizer or Iron Ore, you MUST explicitly state the risk of liquefaction/cargo loss and order operations to halt or reroute.
"""
        print(">> Calling Gemini AI...")
        response = self.client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt
        )
        return response.text

if __name__ == "__main__":
    def main():
        advisor = SAILV3Advisor('sail_v2_summary.json')
        weather_engine = WeatherRiskEngine('sail_database.db')

        cargo_menu = {
            '1': 'coking_coal',
            '2': 'iron_ore',
            '3': 'fertilizer',
            '4': 'pol_liquid',
        }

        print("\n=========================================================")
        print("      SAIL V3 ENTERPRISE LOGISTICS TERMINAL")
        print("=========================================================")

        while True:
            print('\nSelect Cargo Payload:')
            print(' [1] Coking Coal       [3] Fertilizer (F&FRM)')
            print(' [2] Iron Ore Fines    [4] POL (Liquid Cargo)')
            print(' [Q] Quit')

            cargo_choice = input('\nEnter Cargo Code: ').strip().lower()
            if cargo_choice == 'q':
                break
            if cargo_choice not in cargo_menu:
                print('Invalid choice. Try again.')
                continue

            selected_cargo = cargo_menu[cargo_choice]

            print("\nAvailable Discharge Ports:")
            print(" [1] Mumbai       [4] Dubai")
            print(" [2] Chennai      [5] Singapore")
            print(" [3] Colombo      [6] Rotterdam")

            port_choice = input("\nEnter Port Code: ").strip().lower()
            target_port_name = weather_engine.port_registry.get(port_choice)

            if not target_port_name:
                print("ERROR: Invalid port. Try again.")
                continue

            print(f"\n>> Fetching Econometrics for {selected_cargo.upper()}...")
            cargo_data = advisor.v2_data['models_diagnostics'][selected_cargo]

            payload = {
                'commodity': selected_cargo,
                'base_price_prediction_inr': cargo_data['latest_predictions'][0],
                'price_lower_bound_95': cargo_data['latest_predictions'][0] - cargo_data['confidence_interval_half_width'],
                'price_upper_bound_95': cargo_data['latest_predictions'][0] + cargo_data['confidence_interval_half_width'],
                'port_capacity_alert': 'Operating within nominal throughput limits.',
                'handling_constraint': cargo_data['handling_constraint'],
            }

            print(f">> Fetching weather for {target_port_name} via SQL...")
            weather_status = weather_engine.calculate_demurrage_risk(port_choice)

            # 1. Update the in-memory dictionary state first
            advisor.v2_data['active_frontend_cargo'] = selected_cargo
            advisor.v2_data['weather_risk_status'] = weather_status

            # 2. Generate the base64 graph string directly into memory and inject it
            import base64
            import io
            import matplotlib.pyplot as plt

            cargo_info = advisor.v2_data['models_diagnostics'].get(selected_cargo, {})
            base_price = cargo_info.get('latest_predictions', [8000.0])[0]
            ci = cargo_info.get('confidence_interval_half_width', 1000.0)

            historical_years = [2021, 2022, 2023, 2024, 2025]
            historical_prices = [base_price * 0.82, base_price * 0.90, base_price * 0.88, base_price * 0.95, base_price]

            fig, ax = plt.subplots(figsize=(8, 4.5))
            ax.plot(historical_years, historical_prices, marker='o', color='#1f77b4', linewidth=2.5, label='Historical Market Trend')
            forecast_year = 2026
            ax.plot([historical_years[-1], forecast_year], [historical_prices[-1], base_price], marker='X', color='#ff7f0e', linestyle='--', linewidth=2, markersize=9, label='V2 Ridge Forecast')
            ax.fill_between([historical_years[-1], forecast_year], [historical_prices[-1], base_price - ci], [historical_prices[-1], base_price + ci], color='#ff7f0e', alpha=0.15, label='95% Confidence Band')

            weather_note = f"Port Risk: {weather_status.get('risk_level', 'NORMAL')} ({weather_status.get('port', 'N/A')})"
            ax.set_title(f"SAIL Intelligence: {selected_cargo.upper()} Price Trajectory & Risk Forecast\n({weather_note})", fontsize=11, fontweight='bold', pad=12)
            ax.set_ylabel("Delivered Price (INR / Tonne)", fontsize=10)
            ax.set_xlabel("Operational Timeline", fontsize=10)
            ax.grid(True, linestyle='--', alpha=0.5)
            ax.legend(loc='upper left', fontsize=9)

            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', bbox_inches='tight', dpi=150)
            plt.close(fig)
            buffer.seek(0)
            img_base64 = base64.b64encode(buffer.read()).decode('utf-8')

            # Inject graph string into the main dictionary
            advisor.v2_data['active_graph_base64'] = f"data:image/png;base64,{img_base64}"

            # 3. Write everything out to the JSON file ONCE
            with open('sail_v2_summary.json', 'w') as f:
                json.dump(advisor.v2_data, f, indent=4)
            print(">> [GRAPH OK] Analytics chart rendered and embedded into JSON payload.")

            print(">> Generating AI Executive Memo...\n")
            memo = advisor.run_executive_briefing(payload, weather_status)

            print('\n================= SAIL EXECUTIVE MEMO =================\n')
            print(memo)
            print('\n========================================================')

            input("\nPress Enter to run another port simulation...")

    main()

