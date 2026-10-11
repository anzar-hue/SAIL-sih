# SAIL Logistics Orchestrator V3

**Smart India Hackathon 2026 Prototype**

*A next-generation operations research and autonomous procurement engine for Steel Authority of India Limited (SAIL).*

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

1. [Problem Statement](#problem-statement)
2. [The Business Problem](#the-business-problem)
3. [Our Solution](#our-solution)
4. [The 4-Layer Mathematical Engine](#the-4-layer-mathematical-engine)
5. [Tech Stack](#tech-stack)
6. [Repository Structure](#repository-structure)
7. [How to Run Locally](#how-to-run-locally)
8. [Key Features](#key-features)
9. [Current Limitations](#current-limitations)

---

## The Business Problem

SAIL loses millions of rupees every year to unexpected demurrage penalties, sudden port weather delays, and volatile raw material market shocks.

Tree-based ML models such as XGBoost act as black boxes that a CFO cannot audit. That makes executive buy-in hard for multi-crore procurement decisions.

## Our Solution

We built an **Enterprise War Room Dashboard** powered by a highly auditable **4-layer operations research engine**. Instead of only predicting prices, the system calculates the exact financial threshold at which paying for godown storage is cheaper than risking a delayed vessel.

It combines three inputs:

* live weather data from an external API,
* port capacity limits, and
* Ridge Regression econometrics.

The full matrix is then passed to **Gemini 3.8 Flash**, which generates a decisive, liability-shielded CFO procurement directive.

---

## The 4-Layer Mathematical Engine

| Layer | Name | What it does |
| :--- | :--- | :--- |
| **1** | Baseline Econometrics (Ridge Regression) | Interpretable, linear base pricing built from bunker fuel and global volume datasets. |
| **2** | Market Risk Injection | Dynamic multiplier matrices that simulate geopolitical tension, industry surges, and port closures. |
| **3** | Physical Logistics Constraints | Calculates Panamax freight rates, port capacity bottlenecks, demurrage penalties, and godown storage costs, specific to the chemical nature of the cargo (for example, coal vs. liquid POL). |
| **4** | Procurement Optimizer (Scenario A vs. B) | Compares a **Buy Now** scenario against a **Deferred Purchase** scenario, isolating the exact profit/loss margin and net variance savings. |

```text
 Layer 1               Layer 2                Layer 3                  Layer 4
 Ridge baseline  --->  Market risk       ---> Physical logistics  ---> Procurement optimizer
 price                 multipliers            (freight, demurrage,     (Buy Now vs. Deferred)
                                              port capacity, storage)         |
                                                                              v
                                                                    Gemini CFO directive
```

---

## Tech Stack

| Area | Technologies |
| :--- | :--- |
| **Frontend** | React, Vite, Tailwind CSS, Recharts (dynamic risk-adjusted trajectory curves) |
| **Backend** | Python, Flask (API orchestrator) |
| **Database** | SQLite (`sail_database.db`, offline maritime weather risk fallback) |
| **Machine Learning** | `scikit-learn` (Ridge Regression), `pandas`, `numpy` |
| **Generative AI** | Google Gemini 3.8 Flash (executive CFO directives and margin mitigation) |

---

## Repository Structure

```text
miniML/
├── frontend/                 # React & Vite application
│   ├── src/
│   │   ├── App.jsx           # Main War Room & landing page UI
│   │   ├── main.jsx          # React DOM entry
│   │   └── index.css         # Tailwind directives
│   ├── package.json          # Frontend dependencies
│   └── vite.config.js
├── app.py                    # Flask backend (serves API & Gemini prompts)
├── sail_v3_engine.py         # Core 4-layer math & OR optimizer logic
├── sail_v3_orchester.py      # CLI fallback orchestrator
├── sail_database.db          # Offline weather & port capacity SQLite database
├── requirements.txt          # Python dependencies
└── .env                      # Environment variables (GEMINI_API_KEY)
```

---

## How to Run Locally

You need two terminals: one for the Flask backend and one for the React frontend.

### 1. Start the Flask backend (port 5000)

Open a terminal in the root `miniML/` directory:

```bash
# Install Python dependencies
pip install -r requirements.txt

# Start the Flask API and V3 engine
python app.py
```

Before starting, make sure your `.env` file contains your Gemini API key:

```env
GEMINI_API_KEY=your_key_here
```

### 2. Start the React frontend (port 5173)

Open a **second** terminal:

```bash
# Move to the frontend folder
cd frontend

# Install Node modules (Recharts, Tailwind, Lucide)
npm install

# Start the Vite development server
npm run dev
```

### 3. Launch the app

Open your browser and go to:

```text
http://localhost:5173
```

Click **Launch Forecasting Engine** on the landing page to open the live War Room.

---

## Key Features

* **Auditable AI:** CFOs can see the exact mathematical justification (storage vs. freight vs. demurrage) behind every AI recommendation.
* **Liability shielding:** The system recommends strategic *procurement windows* rather than exact calendar dates, which protects analysts from legal liability.
* **Offline resilience:** If the live weather API fails during a presentation, the system falls back automatically to local SQLite historical weather matrices without crashing.
* **Chemical-aware storage logic:** Holding costs adjust automatically to the cargo (₹150 for coal vs. ₹350 for volatile fertilizers).

---

## Current Limitations

* **Limited data:** The prototype currently runs on only **7 data files, merged into a single database file** (`sail_database.db`). Because data is scarce, the engine cannot yet perform at its full potential.
* **Path to improvement:** Once SAIL provides official maritime data, the models can be retrained on far richer inputs, and prediction accuracy and overall performance should improve significantly.