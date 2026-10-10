import { useState } from 'react';
import { Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Area, ComposedChart } from 'recharts';
import { AlertTriangle, Anchor, ShieldCheck, ChevronDown, ChevronUp } from 'lucide-react';
// Custom Tooltip Component
const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-white border border-gray-200 shadow-md p-3 rounded text-sm min-w-50">
        <div className="font-bold text-gray-800 mb-2 border-b pb-1">{label}</div>
        
        {payload.map((entry, index) => (
          <div key={index} className="flex justify-between items-center py-1 gap-4">
            <span style={{ color: entry.color }} className="font-medium">
              {entry.name}:
            </span>
            <span className="text-gray-700 font-semibold">
              {/* Format number with commas and add currency symbol if needed */}
              {Number(entry.value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>
        ))}
      </div>
    );
  }

  return null;
};

function SAILWarRoom({ onReturn }) {
  // Step 1: Base Inputs
  const [cargo, setCargo] = useState('Iron Ore');
  const [port, setPort] = useState('Haldia');
  const [tonnage, setTonnage] = useState(100000);
  
  // Step 2: Shock Inputs (Gated)
  const [event, setEvent] = useState('none');
  const [months, setMonths] = useState(2);
  
  // UI State
  const [showReasoning, setShowReasoning] = useState(false);
  const [isSimulating, setIsSimulating] = useState(false);

  // Hardcoded sample data to match your backend output (In production, fetch from /api/v3/optimize)
  // Dynamic API State
  const [chartData, setChartData] = useState([
    { month: 'Current', basePrice: 0, shockPrice: 0, storage: 0 }
  ]);
  const [financials, setFinancials] = useState(null);
  const [scenarioData, setScenarioData] = useState(null);
  const [executiveMemo, setExecutiveMemo] = useState("Run a simulation to generate the CFO directive.");

 const handleSimulate = async () => {
    setIsSimulating(true);
    
    try {
      const response = await fetch('http://localhost:5000/api/v3/optimize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cargo: cargo,
          port_name: port,
          tonnage: Number(tonnage),
          event_keyword: event,
          target_months_away: Number(months),
          vessel_type: "Panamax",
          godown_cost_per_tonne_per_month: cargo === 'Fertilizer (F&FRM)' ? 350 : cargo === 'POL (Liquid)' ? 600 : 150
        })
      });

      const result = await response.json();
      
      if (result.status === "success") {
        const data = result.data;
        
        // Calculate Profit/Loss Margin %
        const scenarioA = data.scenario_a_buy_now.total_cost;
        const scenarioB = data.scenario_b_wait.total_cost;
        const marginPercent = ((Math.abs(scenarioA - scenarioB) / Math.max(scenarioA, scenarioB)) * 100).toFixed(2);
        
        // Inject margin into the state
        setFinancials({
          ...data.financial_analysis,
          marginPercent: marginPercent,
          marginType: scenarioA < scenarioB ? 'Profit Edge' : 'Loss Exposure'
        });
        setScenarioData({ a: data.scenario_a_buy_now, b: data.scenario_b_wait });
        
        setExecutiveMemo(result.executive_memo);
        
        // Build 5 data points for a smooth "natural" curve
        const base = data.scenario_b_wait.predicted_base_material_cost / 1000000;
        const shock = data.scenario_b_wait.shock_material_cost / 1000000;
        const curr = data.scenario_a_buy_now.material_cost / 1000000;
        
        setChartData([
          { month: 'Today', basePrice: curr, shockPrice: curr },
          { month: 'Week 2', basePrice: curr - (curr-base)*0.2, shockPrice: curr + (shock-curr)*0.3 },
          { month: 'Month 1', basePrice: (curr + base)/2, shockPrice: (curr + shock)/2 },
          { month: 'Week 6', basePrice: base + (curr-base)*0.1, shockPrice: shock - (shock-curr)*0.1 },
          { month: `Month ${months} (Target)`, basePrice: base, shockPrice: shock }
        ]);
      }
    } catch (error) {
      console.error("API Error:", error);
      setExecutiveMemo("Error connecting to backend.");
    }
    
    setIsSimulating(false);
  };

  return (
    <div className="min-h-screen bg-[#F8FAFC] font-sans">
      {/* SAIL Corporate Navbar */}
      <nav className="bg-[#18316E] text-white p-4 flex justify-between items-center shadow-md">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-white rotate-45 flex items-center justify-center">
            <div className="w-4 h-4 bg-[#18316E]"></div>
          </div>
          <h1 className="text-xl font-bold tracking-wider">SAIL <span className="font-light">| LOGISTICS ORCHESTRATOR V3</span></h1>
        </div>
        
        {/* NEW: Exit Button added next to the War Room text */}
        <div className="flex items-center gap-4">
          <div className="text-sm text-blue-200 hidden md:block">Executive War Room</div>
          <button 
            onClick={onReturn}
            className="bg-white text-[#18316E] hover:bg-gray-200 px-4 py-1.5 rounded text-sm font-bold transition-colors shadow-sm"
          >
            Exit to Home
          </button>
        </div>
      </nav>

      <div className="grid grid-cols-12 gap-6 p-6">
        {/* LEFT PANEL: The Input Gates */}
        <div className="col-span-12 lg:col-span-4 space-y-6">
          
          {/* Gate 1: Baseline Logistics */}
          <div className="bg-white p-6 rounded-lg shadow-sm border-t-4 border-[#18316E]">
            <h2 className="text-lg font-bold text-[#231F20] mb-4 flex items-center gap-2">
              <Anchor size={20} className="text-[#18316E]"/> 1. Baseline Logistics
            </h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-semibold text-gray-600 mb-1">Cargo Type</label>
                <select className="w-full border p-2 rounded" value={cargo} onChange={(e) => setCargo(e.target.value)}>
                  <option>Coking Coal</option>
                  <option>Iron Ore</option>
                  <option>Fertilizer (F&FRM)</option>
                  <option>POL (Liquid)</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-semibold text-gray-600 mb-1">Discharge Port</label>
                <select className="w-full border p-2 rounded" value={port} onChange={(e) => setPort(e.target.value)}>
                  <option>Haldia</option>
                  <option>Paradip</option>
                  <option>Vishakhapatnam</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-semibold text-gray-600 mb-1">Tonnage Required (MT)</label>
                <input type="number" className="w-full border p-2 rounded" value={tonnage} onChange={(e) => setTonnage(e.target.value)} />
              </div>
            </div>
          </div>
          <div>
                <label className="block text-sm font-semibold text-gray-600 mb-1">Prediction Engine</label>
                <select className="w-full border p-2 rounded text-sm text-gray-700 bg-gray-50">
                  <option>Ridge Regression (Active - Auditable)</option>
                  <option>XGBoost (Offline / Blackbox)</option>
                  <option>Random Forest (Offline / Ensembled)</option>
                </select>
              </div>

          {/* Gate 2: Market Shocks (Only unlocked if Gate 1 is filled) */}
          <div className="bg-white p-6 rounded-lg shadow-sm border-t-4 border-[#F97316]">
            <h2 className="text-lg font-bold text-[#231F20] mb-4 flex items-center gap-2">
              <AlertTriangle size={20} className="text-[#F97316]"/> 2. Market Risk Injection
            </h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-semibold text-gray-600 mb-1">Expected Disruption</label>
                <select className="w-full border p-2 rounded" value={event} onChange={(e) => setEvent(e.target.value)}>
                  <option value="none">Business as Usual (None)</option>
                  <option value="industry_needs_rise">Industry Demand Surge</option>
                  <option value="weather_issues">Monsoon / Weather Alert</option>
                  <option value="port_closed">Port Congestion</option>
                  <option value="war">Geopolitical Tension</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-semibold text-gray-600 mb-1">Months to Delivery (Storage Horizon)</label>
                <input type="range" min="0" max="6" className="w-full" value={months} onChange={(e) => setMonths(e.target.value)} />
                <div className="text-right text-sm font-bold text-[#18316E]">{months} Months</div>
              </div>
              
              <button 
                onClick={handleSimulate}
                className="w-full bg-[#18316E] hover:bg-[#231F20] text-white font-bold py-3 rounded transition-colors"
              >
                {isSimulating ? 'Recalculating OR Matrix...' : 'Run CFO Optimization'}
              </button>
            </div>
          </div>
        </div>

        {/* RIGHT PANEL: Analytics & AI Directive */}
        <div className="col-span-12 lg:col-span-8 space-y-6">
          
          {/* KPI Dashboard */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-white p-4 rounded-lg shadow-sm border-l-4 border-green-500">
              <div className="text-sm text-gray-500 font-semibold">Net Variance Savings</div>
              <div className="text-2xl font-bold text-green-600">
                {financials ? `₹${(financials.savings / 1000000).toFixed(2)}M` : '---'}
              </div>
              <div className="text-xs text-gray-400 mt-1">vs. Alternative</div>
            </div>
            
            {/* NEW: Profit/Loss Margin Card */}
            <div className={`bg-white p-4 rounded-lg shadow-sm border-l-4 ${financials?.marginType === 'Profit Edge' ? 'border-blue-500' : 'border-red-500'}`}>
              <div className="text-sm text-gray-500 font-semibold">Financial Margin</div>
              <div className={`text-2xl font-bold ${financials?.marginType === 'Profit Edge' ? 'text-blue-600' : 'text-red-600'}`}>
                {financials ? `${financials.marginPercent}%` : '---'}
              </div>
              <div className="text-xs text-gray-400 mt-1">{financials ? financials.marginType : 'Pending Analysis'}</div>
            </div>

            <div className="bg-white p-4 rounded-lg shadow-sm border-l-4 border-[#18316E]">
              <div className="text-sm text-gray-500 font-semibold">Optimal Strategy</div>
              <div className="text-2xl font-bold text-[#18316E]">
                {financials ? financials.cheapest_option.replace('_', ' ') : '---'}
              </div>
              <div className="text-xs text-gray-400 mt-1">Timeline Window: {months}m</div>
            </div>
            <div className="bg-white p-4 rounded-lg shadow-sm border-l-4 border-[#F97316]">
              <div className="text-sm text-gray-500 font-semibold">Shock Multiplier</div>
              <div className="text-2xl font-bold text-[#F97316]">
                {financials ? `${financials.applied_shock_multiplier}x` : '1.0x'}
              </div>
              <div className="text-xs text-gray-400 mt-1">{event.replace(/_/g, ' ').toUpperCase()}</div>
            </div>
          </div>

          {/* Dynamic Recharts Chart */}
          <div className="bg-white p-6 rounded-lg shadow-sm">
            <h2 className="text-lg font-bold text-[#231F20] mb-4">Risk-Adjusted Price Trajectory (₹ Millions)</h2>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.5} />
                  <XAxis dataKey="month" />
                  <YAxis domain={['auto', 'auto']} />
                  <Tooltip content={<CustomTooltip />} />
                  <Legend />
                  <Area type="natural" dataKey="shockPrice" fill="#F97316" fillOpacity={0.1} stroke="none" name="Risk Exposure Zone" />
                  <Line type="natural" dataKey="basePrice" stroke="#231F20" strokeWidth={2} name="Scenario B (Unshocked)" />
                  <Line type="natural" dataKey="shockPrice" stroke="#F97316" strokeWidth={3} strokeDasharray="5 5" name="Scenario B (Shocked)" />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* AI Executive Memo */}
          <div className="bg-[#F8FAFC] border border-gray-200 p-6 rounded-lg shadow-sm relative overflow-hidden">
            <div className="absolute top-0 left-0 w-2 h-full bg-[#18316E]"></div>
            
            <div className="flex items-center gap-2 mb-3">
              <ShieldCheck className="text-[#18316E]" size={24} />
              <h2 className="text-xl font-black text-[#18316E] tracking-tight">AI CFO DIRECTIVE</h2>
            </div>
            
            {/* whitespace-pre-wrap ensures the AI's line breaks render correctly */}
            <div className="text-gray-800 text-sm leading-relaxed mb-4 whitespace-pre-wrap">
              {executiveMemo}
            </div>
          </div>

          {/* Collapsible Math Justification */}
          <div className="border border-gray-300 rounded bg-white">
            <button 
              onClick={() => setShowReasoning(!showReasoning)}
              className="w-full flex justify-between items-center p-3 text-sm font-bold text-[#231F20] hover:bg-gray-50 transition-colors"
            >
              <span>Read Mathematical Justification</span>
              {showReasoning ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
            </button>
            
            {showReasoning && scenarioData && financials && (
                <div className="p-4 border-t border-gray-200 text-sm text-gray-600 bg-gray-50 space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <h4 className="font-bold text-[#18316E] mb-2">Scenario A (Buy Now)</h4>
                      <ul className="space-y-1">
                        <li>Material: ₹{(scenarioData.a.material_cost / 1e6).toFixed(1)}M</li>
                        <li>Logistics: ₹{(scenarioData.a.logistics_cost / 1e6).toFixed(1)}M</li>
                        <li>Godown: ₹{(scenarioData.a.storage_cost / 1e6).toFixed(1)}M</li>
                        <li className="font-bold text-[#231F20] pt-2 border-t border-gray-300">
                          Total: ₹{(scenarioData.a.total_cost / 1e6).toFixed(1)}M
                        </li>
                      </ul>
                    </div>
                    <div>
                      <h4 className="font-bold text-[#F97316] mb-2">Scenario B (Wait - Risk Adj)</h4>
                      <ul className="space-y-1">
                        <li>Material: ₹{(scenarioData.b.shock_material_cost / 1e6).toFixed(1)}M</li>
                        <li>Logistics: ₹{(scenarioData.b.logistics_cost / 1e6).toFixed(1)}M</li>
                        <li>Demurrage: ₹{(scenarioData.b.demurrage_penalty / 1e6).toFixed(1)}M</li>
                        <li className="font-bold text-[#231F20] pt-2 border-t border-gray-300">
                          Total: ₹{(scenarioData.b.total_cost / 1e6).toFixed(1)}M
                        </li>
                      </ul>
                    </div>
                  </div>
                  <p className="bg-white p-3 border border-gray-200 rounded italic text-xs">
                    Alternative Risk: Waiting exposes SAIL to severe market volatility and a {cargo} price escalation of {((financials.applied_shock_multiplier - 1) * 100).toFixed(0)}%. Speculating introduces unacceptable exposure to supply tightness and costly blast furnace feedstock disruptions.
                  </p>
                </div>
              )}
          </div>
        </div>
      </div>
    </div>
  );
}
// --- LANDING PAGE COMPONENT ---
function LandingPage({ onLaunch }) {
  return (
    <div className="min-h-screen bg-white flex flex-col font-sans">
      {/* Corporate Header */}
      <header className="bg-[#18316E] text-white p-4 flex justify-between items-center shadow-md">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-white rotate-45 flex items-center justify-center">
            <div className="w-4 h-4 bg-[#18316E]"></div>
          </div>
          <h1 className="text-xl font-bold tracking-wider">SAIL <span className="font-light">| STEEL AUTHORITY OF INDIA</span></h1>
        </div>
        <nav className="hidden md:flex gap-6 text-sm font-semibold text-blue-100">
          <a href="https://sail.co.in/en/company/about-us" target="_blank" rel="noreferrer" className="hover:text-white transition">About Us</a>
          <a href="https://sail.co.in/en/sail-management/chairman" target="_blank" rel="noreferrer" className="hover:text-white transition">Leadership</a>
          <a href="https://sail.co.in/en/contact-us" target="_blank" rel="noreferrer" className="hover:text-white transition">Contact</a>
        </nav>
      </header>

      {/* Hero Section */}
      <main className="flex-1 flex flex-col items-center justify-center text-center p-6 bg-linear-to-b from-[#F8FAFC] to-white">
        <div className="max-w-3xl space-y-6">
          <div className="inline-block bg-[#F97316] text-white px-4 py-1 rounded-full text-xs font-bold tracking-widest mb-4">
            SIH 2026 PROTOTYPE
          </div>
          <h2 className="text-4xl md:text-5xl font-black text-[#231F20] leading-tight">
            Next-Generation <br/><span className="text-[#18316E]">Operations Research Engine</span>
          </h2>
          <p className="text-gray-600 text-lg">
            This module is a specialized predictive logistics environment developed for the Smart India Hackathon. It utilizes 4-layer mathematical modeling and AI to optimize bulk material procurement, mitigate demurrage, and forecast market shocks.
          </p>
          
          <div className="pt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
            <button 
              onClick={onLaunch}
              className="bg-[#18316E] hover:bg-[#231F20] text-white px-8 py-4 rounded font-bold text-lg shadow-lg hover:shadow-xl transition-all transform hover:-translate-y-1 w-full sm:w-auto"
            >
              Launch Forecasting Engine
            </button>
            <a 
              href="https://sail.co.in" 
              target="_blank" 
              rel="noreferrer"
              className="px-8 py-4 rounded font-bold text-lg text-[#18316E] border-2 border-[#18316E] hover:bg-gray-50 transition-colors w-full sm:w-auto"
            >
              Return to Official SAIL Site
            </a>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-[#231F20] text-gray-400 p-6 text-center text-xs">
        <p>Disclaimer: This is a prototype application built for SIH 2026. Data and forecasts generated are for demonstration purposes only.</p>
        <p className="mt-2">Not an official deployment of Steel Authority of India Limited.</p>
      </footer>
    </div>
  );
}

// --- MAIN APP ROUTER ---
export default function App() {
  const [currentView, setCurrentView] = useState('landing');

  return (
    <>
      {currentView === 'landing' ? (
        <LandingPage onLaunch={() => setCurrentView('dashboard')} />
      ) : (
        <SAILWarRoom onReturn={() => setCurrentView('landing')} />
      )}
    </>
  );
}