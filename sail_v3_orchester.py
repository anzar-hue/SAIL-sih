import sqlite3
import json
import os
import requests
from dotenv import load_dotenv
from google import genai
from sail_v3_engine import SAIL_V3_Operations_Engine
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
    def __init__(self):
        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    def run_executive_briefing(self, optimization_data):
        prompt = f"""
        You are the Director of Commercial Logistics at SAIL.
        DATA: {json.dumps(optimization_data, indent=2)}
        
        Output strictly in this 3-part format:
        ### 1. THE VERDICT
        ### 2. THE MATH JUSTIFICATION
        ### 3. ALTERNATIVE RISK
        """
        response = self.client.models.generate_content(model="gemini-3.8-flash", contents=prompt)
        return response.text

if __name__ == "__main__":
    def main():
        advisor = SAILV3Advisor()
        v3_engine = SAIL_V3_Operations_Engine()
        
        print("\n=========================================================")
        print("      SAIL V3 CFO LOGISTICS TERMINAL")
        print("=========================================================")

        while True:
            # 0. Cargo Inputs
            print("\n[0] Select Cargo Payload:")
            print(" [1] Coking Coal  [2] Iron Ore Fines  [3] Fertilizer (F&FRM)  [4] POL (Liquid)")
            cargo_choice = input("Cargo Code: ").strip()
            
            # Simulated baseline economics for each cargo type
            cargo_profiles = {
                '1': {'name': 'Coking Coal', 'current_base': 22000.0, 'future_base': 21500.0, 'storage': 150.0},
                '2': {'name': 'Iron Ore', 'current_base': 8000.0, 'future_base': 7800.0, 'storage': 100.0},
                '3': {'name': 'Fertilizer', 'current_base': 45000.0, 'future_base': 46000.0, 'storage': 350.0},
                '4': {'name': 'POL (Liquid)', 'current_base': 65000.0, 'future_base': 67000.0, 'storage': 600.0}
            }
            active_cargo = cargo_profiles.get(cargo_choice, cargo_profiles['1'])

            # 1. Base Inputs
            print("\n[1] Select Port: [1] Haldia  [2] Paradip  [3] Vishakhapatnam")
            port_choice = input("Port Code: ").strip()
            port_map = {'1': 'Haldia', '2': 'Paradip', '3': 'Vishakhapatnam'}
            port_name = port_map.get(port_choice, 'Haldia')

            tonnage = float(input(f"Enter Required Tonnage for {active_cargo['name']} (e.g., 100000): ") or 100000)
            
            # 2. Market Shock Inputs
            print("\n[2] Select Expected Market Event:")
            print(" [none] [war] [weather_issues] [industry_needs_rise] [port_closed]")
            event_keyword = input("Event Keyword: ").strip().lower() or "none"
            
            target_months = int(input("Months until physical need (Godown Storage Time): ") or 0)

            print("\n>> Executing Layer 4 OR Math...")
            # 3. Run the Math with dynamic cargo data
            result = v3_engine.optimize_procurement(
                current_base=active_cargo['current_base'],
                predicted_future_base=active_cargo['future_base'],
                tonnage=tonnage,
                vessel_type="Panamax",
                port_name=port_name,
                event_keyword=event_keyword,
                target_months_away=target_months,
                godown_cost_per_tonne_per_month=active_cargo['storage'],
                cargo=active_cargo['name']
            )
            
            # Inject cargo name into the result so Gemini knows what it is analyzing
            result['cargo_type'] = active_cargo['name']

            print(">> Generating AI CFO Memo...\n")
            memo = advisor.run_executive_briefing(result)

            print('\n================= CFO DIRECTIVE =================\n')
            print(memo)
            print('\n=================================================')

            if input("\nRun another scenario? (y/n): ").lower() != 'y': break

    main()