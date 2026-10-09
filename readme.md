# SAIL: Autonomous Logistics & Strategic Raw Materials Terminal

> **Smart India Hackathon (SIH) 2026**
> **Problem Statement ID:** `SIH2026006`
> **Organization:** Steel Authority of India Limited (SAIL), Ministry of Steel
> **Domain:** AI-Driven Bulk Material Procurement, Dynamic Demurrage Risk Mitigation & Port Capacity Optimization

---

## Executive Presentation Deck

Detailed architecture breakdowns, presentation decks, and executive flow diagrams are available on Google Drive:

📄 **[Access the SAIL Architecture & Logistics Deck (Google Drive)](PASTE_YOUR_LINK_HERE)**

---

## 1. Problem Statement & Operational Context

Integrated steel plants under the Steel Authority of India Limited (SAIL) rely heavily on international supply corridors for metallurgical raw materials, primarily **Australian Premium Coking Coal**, along with domestic and imported movements of **Iron Ore, Limestone/Fertilizer raw materials (F&FRM), and Liquid Fuels (POL)**.

Procurement desks face severe, recurring operational bottlenecks:

* **Decoupled financial and maritime intelligence:** Procurement desks buy commodity forward contracts based on market pricing, but lack visibility into physical port congestion and maritime weather.
* **Severe demurrage surcharges:** When Panamax or Capesize bulk carriers arrive during heavy monsoons or port berthing bottlenecks, offloading halts. Demurrage penalties exceed **$18,000/day** per vessel.
* **Chemical cargo degradation:** Maritime moisture induces spontaneous combustion in coking coal, liquefaction (turning into slurry) in iron ore fines, and complete dissolution in water-soluble fertilizers.
* **Infrastructure handling ceilings:** Models that predict volume without considering national port handling limits produce unrealistic supply plans.

---

## 2. Proposed Solution

The **SAIL Autonomous Logistics & Strategic Raw Materials Terminal** links econometric spot price modeling directly with maritime terminal operations in a unified decision dashboard.

Rather than relying on unconstrained LLM text generation to guess market numbers, the system uses a **multi-tier microservices architecture**:

1. **Local deterministic ML core:** Scikit-Learn algorithms compute delivered import prices with calibrated 95% confidence intervals and validation metrics.
2. **Maritime and port risk layer:** An automated risk engine checks physical port handling capacities and maritime weather (live API with offline SQL fallback), computing exact vessel delay days and demurrage exposure.
3. **Constrained AI briefing generator:** Google Gemini ingests the verified numbers, chemical handling constraints, and operational data to draft clear, boardroom-ready C-suite memos.
4. **Full-stack C-suite dashboard:** A React (Vite) interface powered by a Python Flask REST backend, displaying live KPI metrics, chemical alerts, interactive memo views, and in-memory rendered price trajectory charts.

---

## 3. Technology Stack & Multi-Tier Architecture

### System Architecture Pipeline

```text
 [ External Weather API / Offline SQLite DB ]     [ Historical Macro & Commodity Datasets ]
                    |                                              |
                    v                                              v
       +--------------------------+                 +--------------------------+
       |    WeatherRiskEngine     |                 |       SAILEngineV2       |
       | - Live Open-Meteo API    |                 | - StandardScaler         |
       | - SQLite DB failover     |                 | - Ridge Regression       |
       | - Demurrage math engine  |                 | - 95% confidence bounds  |
       +------------+-------------+                 +------------+-------------+
                    |                                            |
                    +---------------------+----------------------+
                                          |
                                          v
                             +--------------------------+
                             |   sail_v2_summary.json   |
                             |  (Unified State Payload) |
                             +------------+-------------+
                                          |
                    +---------------------+---------------------+
                    |                                           |
                    v                                           v
       +--------------------------+                +--------------------------+
       |   Flask REST API Server  |                |     Google Gemini AI     |
       | - Endpoint: /api/simulate|                | - Constrained prompt     |
       | - Base64 Matplotlib plot |                | - Chemical safety checks |
       +------------+-------------+                +------------+-------------+
                    |                                           |
                    +---------------------+---------------------+
                                          |
                                          v
                             +--------------------------+
                             |    React + Tailwind UI   |
                             | - Dark/Light C-suite view|
                             | - Live commodity toggles |
                             | - Responsive KPI grid    |
                             +--------------------------+
```

### Core Technologies

* **Frontend:** React 18, Vite, Tailwind CSS, Lucide Icons
* **Backend framework:** Python Flask, Flask-CORS
* **Machine learning and analytics:** Scikit-Learn (`Ridge`, `StandardScaler`, `PolynomialFeatures`), Pandas, NumPy
* **Data visualization:** Matplotlib (headless `Agg` buffer serialized directly into React-ready Base64 image strings)
* **Database and fallback storage:** SQLite3 (`sail_database.db`) with parameterized queries for SQL injection protection
* **External APIs and generative AI:** Open-Meteo Marine Forecast API, Google Gemini AI (`google-genai` SDK)

### Backend Endpoints

| Method | Endpoint | Purpose |
| :--- | :--- | :--- |
| `GET` | `/api/dashboard-data` | Returns the unified state payload (`sail_v2_summary.json`). |
| `POST` | `/api/simulate` | Accepts `{ "cargo": "...", "port": "..." }` and returns the recalculated payload. |

---

## 4. Dataset Directory & Pipeline Roles

| File Name | Primary Attributes / Columns | Pipeline Role |
| :--- | :--- | :--- |
| `coal.csv` | `financial_year`, `country`, `coal_type`, `quantity_million_tonnes`, `amount_inr_crore`, `price_inr_per_tonne` | Historical import pricing ground truth for Australian Coking Coal. |
| `rawfuel.csv` | `year`, `month`, `bix_global_avg_usd_per_tonne` | Global bunker fuel index tracking maritime shipping overhead. |
| `exchange_rate_india.csv` | `year`, `month`, `usd_inr_monthly_average` | Currency conversion benchmark used to standardize import metrics to INR. |
| `economic_raw_port_cargo_volume_india (1).csv` | `financial_year`, `coal_000_tonnes`, `total_cargo_000_tonnes` | Macro port throughput tracking domestic bulk intake velocity. |
| `vessels.csv` | `category`, `dwt_mt`, `fuel_consumptio_mt/day` | Panamax vessel specifications (75,205 MT capacity, 35 MT/day burn). |
| `member_3_weather_raw_10000_demo-1.xlsx` | `timestamp_utc`, `location_name`, `wind_speed_knots`, `significant_wave_height_m`, `weather_event`, `extreme_event_flag` | 10,000 real maritime observations across key hubs (Mumbai, Chennai, Rotterdam, Dubai, etc.). |
| `ports.csv` / Ministry reports | `Year`, `Port capacity`, `Traffic Handled`, commodity breakdowns | Ministry of Ports throughput ceilings (e.g., Coal capped at 200.0 MT). |

---

## 5. Machine Learning Models & Analytical Methodology

### 5.1 Econometric Price Modeling (Ridge Regression)

The model estimates delivered import prices per tonne ($y$) using international fuel overhead and port intake throughput.

* **Standardization (Z-score):** Prevents large volume metrics (on the order of $10^5$ tonnes) from distorting low-magnitude exchange rates during gradient optimization:

  $$z = \frac{x - \mu}{\sigma}$$

* **Regularization ($L_2$ penalty):** Addresses strong collinearity between freight calculations and global fuel movements:

  $$\min_{w} \left( \lVert y - Xw \rVert_2^2 + \alpha \lVert w \rVert_2^2 \right)$$

* **95% confidence interval bands:** Instead of providing only a point prediction, the engine calculates operational risk ranges using the residual standard deviation:

  $$\hat{y} \pm 1.96 \cdot \sigma_{\text{residuals}}$$

### 5.2 Multi-Commodity Diagnostics & Strict Handling Rules

| Commodity | Base Price | Risk Band | Handling Constraint |
| :--- | :--- | :--- | :--- |
| **Coking Coal** | ₹8,066.45/t | ₹5,908.21 – ₹10,224.69 | Spontaneous combustion risk if stacked wet. |
| **Iron Ore Fines** | ₹4,250.00/t | ₹3,600.00 – ₹4,900.00 | High moisture causes liquefaction (ore turns into fluid mud); discharge halts during heavy rain. |
| **Fertilizer (F&FRM)** | ₹28,400.00/t | ₹27,200.00 – ₹29,600.00 | Water-soluble chemical cargo; precipitation causes immediate dissolution and total cargo loss. |
| **POL Liquid** | ₹65,200.00/t | ₹62,100.00 – ₹68,300.00 | Discharged via pipeline manifolds; surface winds above 25 knots force marine hose disconnection. |

### 5.3 Tactical Demurrage Risk Formulation

The risk engine evaluates weather across Mumbai, Chennai, Colombo, Dubai, Singapore, and Rotterdam:

$$\text{Demurrage Liability (INR)} = \Delta d \times \text{Daily Panamax Charter Rate (USD)} \times \text{USD/INR Rate}$$

* Standard Panamax charter: **$18,000/day** at **₹83.50/$** (about ₹1,503,000/day).
* Delay days ($\Delta d$) scale with conditions:

| Condition | Delay ($\Delta d$) |
| :--- | :--- |
| Clear | 0 days |
| Chop / elevated wind | 1.0 day |
| Heavy rain / waves above 2.5 m | 3.5 days |
| Cyclone / extreme alert | 6.0 days |

---

## 6. Technical Limitations & Data Bottlenecks

* **Historical data sparsity:** Merging disparate public datasets across identical annual dates left only **7 complete multi-variable training records**.
* **The error floor:** The resulting Mean Absolute Error (**₹1,286.86/tonne**) and MAPE (**17.86%**) represent a practical limit for this small sample. Ridge regression prevents overfitting, but it cannot extrapolate patterns that are missing from the historical records.
* **Public vs. commercial data constraints:** Public reports provide only annual or retrospective monthly aggregations. Access to commercial data feeds (such as daily S&P Global Platts indices, the Baltic Dry Index, or vessel AIS transponder feeds) would let this architecture train on thousands of continuous daily updates and significantly lower prediction error.

---

## 7. Future Roadmap

* **Granular time-series streams:** Replace annual tables with daily transactional import records and real-time customs port manifests.
* **Direct telemetry logging and continuous retraining:** Log all live predictions alongside actual clearance prices in SQLite to monitor data drift and trigger automated model updates.
* **Downstream production linking:** Incorporate domestic steel demand indicators, blast furnace run-rates, and rail rake availability from port yards to manufacturing hubs.
* **High-performance C++ core:** Migrate large-scale analytical transformations to a native C++ engine exposed via `pybind11` wrappers for low-latency execution.

---

## 8. Local Setup & Execution Guide

### Prerequisites

* Python 3.10+
* Node.js v18+ and npm

### Step 1: Clone the Repository & Set Up a Virtual Environment

```bash
git clone https://github.com/<YOUR_USERNAME>/SAIL-Logistics-Terminal.git
cd SAIL-Logistics-Terminal

python -m venv venv

# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### Step 2: Environment Configuration (`.env`)

The repository does **not** include API keys. To enable live Gemini AI executive briefings:

1. Generate a free API key at [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Create a `.env` file in the project root:

```env
GEMINI_API_KEY="your_actual_api_key_here"
```

If no API key is provided, the backend falls back to local diagnostic briefings.

### Step 3: Initialize the SQLite Database

Migrate the raw CSV and Excel datasets into the local database:

```bash
python csv_to_sql.py
```

### Step 4: Build the Frontend & Run the Application

```bash
# Compile the React interface
cd frontend
npm install
npm run build
cd ..

# Start the Flask server
python app.py
```

Open your browser and go to:

```text
http://localhost:5000
```

For development with hot reloading, run `npm run dev` inside `frontend/` (served on port `5173`) while `app.py` runs on port `5000`
