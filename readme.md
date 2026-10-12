# SAIL Logistics Orchestrator V3

**Smart India Hackathon 2026 Prototype**

*An auditable operations research and procurement decision engine for bulk raw-material imports at Steel Authority of India Limited (SAIL), one that gets more accurate every time a buyer records what they actually paid.*

---

## Problem Statement

| | |
| :--- | :--- |
| **Hackathon** | Smart India Hackathon (SIH) 2026 |
| **Problem Statement ID** | `SIH26006` |
| **Title** | Development of an Intelligent Freight Forecasting Model for Optimized Vessel Chartering and Bulk Cargo Procurement from overseas to East Coast of India |
| **Organization** | Ministry of Steel (Department: SAIL, Steel Authority of India Limited) |
| **Category** | Software |
| **Theme** | Transportation & Logistics |

---

## Table of Contents

1. [Overview](#overview)
2. [Self-Learning Feedback Loop](#self-learning-feedback-loop)
3. [Key Capabilities](#key-capabilities)
4. [The 4-Layer Mathematical Engine](#the-4-layer-mathematical-engine)
5. [Architecture and Tech Stack](#architecture-and-tech-stack)
6. [API Reference](#api-reference)
7. [Repository Structure](#repository-structure)
8. [Getting Started](#getting-started)
9. [Demo Walkthrough](#demo-walkthrough)
10. [Data Sources and Assumptions](#data-sources-and-assumptions)
11. [Current Limitations and Roadmap](#current-limitations-and-roadmap)

---

## Overview

SAIL loses significant sums each year to demurrage penalties, weather-related port delays and volatile raw-material markets. Black-box models such as XGBoost make this worse in one respect: a CFO cannot audit them, which makes multi-crore procurement decisions hard to sign off.

V3 replaces the black box with a transparent **4-layer operations research engine**. Instead of only predicting a price, it answers the questions a procurement desk actually asks:

* **Where should we buy from?** It ranks import origins by landed cost for the selected cargo.
* **When should we order?** It costs every candidate order date between today and the delivery deadline and recommends an order *window*.
* **What does it cost us to be wrong?** Every figure (material, freight, bunker fuel, demurrage, storage) is itemised for audit.
* **Did the model get it right?** The buyer records the actual price paid, and the engine measures its own error and corrects future estimates.

A Gemini-generated executive memo summarises the numbers for the board, and a local briefing engine takes over automatically if the AI service is unavailable.

---

## Self-Learning Feedback Loop

This is the feature that separates V3 from a one-shot calculator: **the system improves itself from a single user input, the actual price paid.**

```text
  1. PREDICT          2. LOG               3. BUY                4. RECORD ACTUAL
  Optimizer runs  ->  Prediction saved ->  Order placed,      ->  Buyer enters the price
  and recommends      to history with      suggested window      per tonne actually paid
  origin + window     its order window     passes                in the History tab
        ^                                                                  |
        |                                                                  v
  6. CORRECT FUTURE  <-------------------------------------------  5. MEASURE ERROR
  Estimates for that cargo are scaled by the                        Variance, MAE, MAPE and
  learned error; a notice tells the user                            bias are updated live
```

**How it works**

1. Every date-based optimization is stored in the `prediction_history` table (SQLite) together with its suggested order window. Re-running identical inputs updates the existing entry, so experimentation does not flood the history.
2. One week after the suggested order date, a **notification** appears in the top-right corner asking the buyer to record the actual price. It appears once, and disappears when the buyer opens History or dismisses it.
3. The buyer enters the purchase price per tonne in the History tab. The system stores the variance and refreshes accuracy statistics (mean absolute error, mean absolute % error, and bias).
4. Once **3 or more purchases** of a cargo are recorded, the engine applies a **calibration factor** to that cargo's future price estimates. The factor is the average ratio of actual to predicted price over the last 10 purchases, limited to ±20%. The dashboard displays the correction in use.

**Safeguards**

* Entries more than 50% away from the prediction require explicit confirmation, so a typing error cannot corrupt the model.
* Calibration is stored per prediction so earlier corrections are not double-counted.
* A new cargo starts uncalibrated (factor 1.0) and never changes without real data.

**What this is, precisely:** a transparent bias-correction loop that learns from realised outcomes. A full statistical refit of the Ridge baseline on accumulated monthly history is the planned next step once enough data exists (see [Roadmap](#current-limitations-and-roadmap)).

---

## Key Capabiliti453sw33es

| Capability | Description |
| :--- | :--- |
| **Origin intelligence** | Each cargo has its own import origins (for example Australia, USA, Canada, Mozambique and Russia for coking coal). The engine ranks them by landed cost per tonne and explains the recommendation with reasons generated from the numbers, not by the AI. |
| **Date-aware order timing** | The user enters today's date and the required delivery date. The optimizer costs weekly candidate order dates, accounting for transit time, weather delay and storage, and recommends a window of about three days either side of the best date. Exact calendar days are deliberately withheld from the AI memo. |
| **Cargo-aware market shocks** | Disruptions such as war, monsoon alerts, port congestion and demand surges affect each cargo differently. Weather hits iron ore and fertilizer hardest; war hits POL hardest. The sensitivities live in two lookup tables so they can be replaced with data-fitted values. |
| **Chemical-aware logistics** | Storage cost, handling constraints and weather exposure reflect each cargo's physical risk: spontaneous combustion in wet coking coal, liquefaction of iron ore fines, dissolution of fertilizer, and the wind limit for POL manifolds. |
| **Real import records** | Coking-coal price levels and supply volumes by origin are calculated from SAIL import records stored in `sail_database.db` (last three financial years). |
| **Port capacity and demurrage** | Port handling limits are enforced, with demurrage charged in rupees from USD day rates for any delay beyond capacity or weather. |
| **Full audit trail** | A "Mathematical Justification" panel itemises material, logistics, demurrage and storage for each scenario. |
| **Resilient AI briefing** | Gemini 3.8 Flash writes the executive memo. If the API is unavailable, an offline briefing built from the same numbers is shown and labelled as such. Identical scenarios are cached to conserve API quota. |

---

## The 4-Layer Mathematical Engine

| Layer | Name | What it does |
| :--- | :--- | :--- |
| **1** | Baseline Econometrics | Interpretable Ridge-regression base pricing from bunker fuel, global volume and exchange-rate data. Reference prices feed the optimizer, adjusted by the calibration factor learned from recorded purchases. |
| **2** | Market Risk Injection | Cargo-specific multiplier and delay tables simulating geopolitical tension, industry surges, weather alerts and port congestion. |
| **3** | Physical Logistics Constraints | Origin freight, bunker fuel (vessel burn x transit days), transit time, port capacity limits, demurrage and godown storage cost. |
| **4** | Procurement Optimizer | Compares every candidate order date for the chosen origin and ranks all origins, isolating the saving versus buying now or waiting. |

---

## Architecture and Tech Stack

```text
  React + Vite dashboard  <---- REST / JSON ---->  Flask API (app.py)
  (Optimizer | History)                                  |
                                    +--------------------+--------------------+
                                    |                    |                    |
                            sail_v3_engine.py     SQLite database      Gemini 3.8 Flash
                            4-layer OR engine     sail_database.db     executive memo
                            origins, order dates  imports, weather,    (falls back to
                            calibration inputs    prediction_history   local_memo.py)
```

| Area | Technologies |
| :--- | :--- |
| **Frontend** | React, Vite, Tailwind CSS, Recharts, Lucide Icons, DOMPurify |
| **Backend** | Python, Flask, Flask-CORS |
| **Database** | SQLite (`sail_database.db`) with parameterized queries |
| **Machine learning** | scikit-learn (Ridge Regression), pandas, numpy |
| **Generative AI** | Google Gemini 3.8 Flash (`google-genai`) |

---

## API Reference

| Method | Endpoint | Purpose |
| :--- | :--- | :--- |
| `GET` | `/api/v3/origins` | Import origins available for each cargo. |
| `POST` | `/api/v3/optimize` | Runs the optimizer. Send `cargo`, `origin`, `port_name`, `tonnage`, `event_keyword`, `current_date`, `delivery_date`. Returns scenarios, order window, origin ranking, calibration info and the executive memo. A request without `delivery_date` uses the legacy months-based path. |
| `GET` | `/api/v3/history` | All logged predictions with accuracy statistics. |
| `GET` | `/api/v3/history/due?as_of=YYYY-MM-DD` | Predictions whose notification is due. |
| `POST` | `/api/v3/history/<id>/actual` | Records the actual price paid (`actual_price`, optional `confirm`). |
| `POST` | `/api/v3/history/<id>/dismiss` | Dismisses a notification. |
| `POST` | `/api/simulate` | V2 dashboard route (live weather risk, trajectory chart). |

---

## Repository Structure

```text
miniML/
├── frontend/                 # React & Vite application
│   ├── src/
│   │   ├── App.jsx           # Landing page, War Room, History tab, notifications
│   │   ├── main.jsx
│   │   └── index.css
│   ├── package.json
│   └── vite.config.js
├── app.py                    # Flask API, history and calibration routes, Gemini prompt
├── sail_v3_engine.py         # 4-layer engine: origins, order timing, shocks, logistics
├── local_memo.py             # Offline executive briefing used when the AI is unavailable
├── setup_history.py          # Creates / upgrades the prediction_history table
├── sail_v3_orchester.py      # CLI orchestrator
├── sail_v2_engine.py         # V2 econometric engine
├── sail_database.db          # SQLite: imports, fuel, FX, weather, prediction history
├── requirements.txt
└── .env                      # GEMINI_API_KEY (never commit this file)
```

---

## Getting Started

### 1. Backend (port 5000)

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_key_here
```

Start the server. The history table is created or upgraded automatically on startup:

```bash
python app.py
```

If no API key is set, or the quota is exhausted, the dashboard shows the offline briefing instead.

### 2. Frontend (port 5173)

In a second terminal:

```bash
cd frontend
npm install
npm install dompurify
npm run dev
```

### 3. Open the app

Go to `http://localhost:5173` and click **Launch Forecasting Engine**.

---

## Demo Walkthrough

1. Choose **Coking Coal**, an origin and a port, then set the **delivery date** a couple of months ahead. Run the optimization and review the recommended origin, the order window and the cost breakdown.
2. Open **Origin Intelligence** to see why another origin is cheaper or why one is flagged.
3. To demonstrate the feedback loop, move **Today's Date** forward by 8 days. A notification appears asking for the actual price.
4. Click **Go to History**, enter the price you paid, and watch the error statistics update.
5. After three recorded purchases of the same cargo, run the optimizer again: a note shows the calibration now applied to its estimates.

---

## Data Sources and Assumptions

| Item | Source | Status |
| :--- | :--- | :--- |
| Coking-coal import price and volume by origin | `coking_coal` table in `sail_database.db` (last 3 financial years) | **Real records** |
| Freight, transit time and weather delay per origin | Engineering estimates | Placeholder, pending official data |
| Origins and prices for iron ore, fertilizer and POL | Engineering estimates | Placeholder, pending official data |
| Cargo-specific shock and delay sensitivities | Domain reasoning | Placeholder, designed to be replaced by fitted values |
| Bunker fuel price | Assumed USD 600 per tonne | Placeholder |
| Weather observations (10,000 rows) | Demo dataset labelled non-authoritative | Synthetic |

---

## Current Limitations and Roadmap

* **Limited training data:** The prototype runs on seven source datasets merged into a single database. Because data is scarce, the engine cannot yet operate at full potential. Official maritime and procurement data will allow the models to be retrained and accuracy to improve significantly.
* **Price path is assumed:** Within a delivery window, prices move linearly between today's price and the predicted price. A true monthly time-series forecast (for example SARIMAX) needs historical series from SAIL.
* **Calibration is bias correction, not a refit:** The feedback loop corrects average error per cargo. Refitting the Ridge baseline on accumulated history is planned once enough observations exist.
* **Prices are not quality-adjusted:** Origin price levels are import averages and do not account for coal grade differences.
* **Freight is estimated:** Freight is a per-origin estimate and not yet a forecast, so a dedicated freight forecasting model is a priority roadmap item.
* **Weather in the V3 optimizer:** Weather exposure is modelled through event-based delay assumptions. Live forecast integration (Open-Meteo, already used by the V2 route) is planned for the date-based optimizer.
* **Origin screening:** Origins carrying sanctions or compliance risk are flagged and excluded from automatic recommendations pending a compliance review.

**Roadmap:** official SAIL data integration, time-series price and freight forecasting, automated Ridge refits from the history table, live weather forecasts for the arrival date, and live exchange-rate feeds.