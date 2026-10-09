import { useState, useEffect, useCallback, useMemo } from "react";
import {
  TrendingDown, Anchor, Wind, AlertTriangle, ShieldCheck, FileText, BarChart3,
  RefreshCw, Sun, Moon, ChevronDown, Wifi, WifiOff, Flame, Mountain, Sprout, Droplets,
} from "lucide-react";

/* ───────────────────────── Config & constants ───────────────────────── */

const API_BASE = "";
const NAVY = "#033557";
const BLUE = "#084298";
const DEMURRAGE_PER_DAY = 18000 * 83.5; // Panamax USD/day x USD/INR = ₹1,503,000

const CARGOES = [
  { id: "coking_coal", label: "Coking Coal", sub: "Australia", Icon: Flame, ceiling: "coal_ceiling_mt" },
  { id: "iron_ore", label: "Iron Ore Fines", sub: "Bulk, moisture-sensitive", Icon: Mountain, ceiling: "iron_ore_ceiling_mt" },
  { id: "fertilizer", label: "Fertilizer (F&FRM)", sub: "Water-soluble", Icon: Sprout, ceiling: "fertilizer_ceiling_mt" },
  { id: "pol_liquid", label: "POL (Liquid Bulk)", sub: "Pipeline manifold", Icon: Droplets, ceiling: null },
];
const PORTS = ["Mumbai", "Chennai", "Colombo", "Dubai", "Singapore", "Rotterdam"];

// Used only when the Flask backend is unreachable
const PORT_WX = {
  Mumbai: { wind: 14.2, rain: 0, cyclone: false },
  Chennai: { wind: 31.0, rain: 8.4, cyclone: true },
  Colombo: { wind: 16.0, rain: 6.5, cyclone: false },
  Dubai: { wind: 12.0, rain: 0, cyclone: false },
  Singapore: { wind: 9.0, rain: 3.1, cyclone: false },
  Rotterdam: { wind: 27.4, rain: 1.2, cyclone: false },
};

const DEFAULT_DATA = {
  system_status: "SAIL_V2_OPERATIONAL",
  port_capacity_limits: { total_major_ports: 1717.96, coal_ceiling_mt: 200.0, iron_ore_ceiling_mt: 75.0, fertilizer_ceiling_mt: 25.0 },
  models_diagnostics: {
    coking_coal: {
      mae: 1286.86, mape_percent: 17.86, is_applicable: false, confidence_interval_half_width: 2158.24,
      correlations: { price_inr_per_tonne: 1.0, fuel_price_inr: -0.2546, coal_000_tonnes: -0.8021 },
      latest_predictions: [8066.45, 8987.37],
      handling_constraint: "Moderate risk of spontaneous combustion if stacked wet.",
    },
    iron_ore: {
      mae: 412.5, mape_percent: 9.8, is_applicable: true, confidence_interval_half_width: 650.0,
      correlations: { throughput: -0.74, fuel: -0.18 }, latest_predictions: [4250.0],
      handling_constraint: "CRITICAL: High moisture causes liquefaction (cargo turns into fluid mud). Halt discharge in heavy rain.",
    },
    fertilizer: {
      mae: 1100.2, mape_percent: 7.45, is_applicable: true, confidence_interval_half_width: 1200.0,
      correlations: { throughput: -0.61, fuel: -0.32 }, latest_predictions: [28400.0],
      handling_constraint: "CRITICAL: Water-soluble chemical cargo. Any rain during discharge leads to total cargo dissolution.",
    },
    pol_liquid: {
      mae: 2450.0, mape_percent: 6.2, is_applicable: true, confidence_interval_half_width: 3100.0,
      correlations: { throughput: -0.45, fuel: 0.85 }, latest_predictions: [65200.0],
      handling_constraint: "Pipeline manifold discharge. High surface winds (>25 knots) force marine hose disconnection.",
    },
  },
  active_frontend_cargo: "coking_coal",
  weather_risk_status: {
    port: "Mumbai", data_source: "LIVE_API", wind_speed_knots: 14.2,
    risk_level: "LOW / CLEAR BERTHING", estimated_delay_days: 0.0, demurrage_exposure_inr: 0.0,
  },
  active_graph_base64: null,
};

/* ───────────────────────── API service helper ───────────────────────── */

async function request(path, options = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 4000);
  try {
    const res = await fetch(`${API_BASE}${path}`, { ...options, signal: ctrl.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

const api = {
  getDashboard: () => request("/api/dashboard-data", { headers: { Accept: "application/json" } }),
  simulate: (body) =>
    request("/api/simulate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
};

// Offline stand-in for the V3 maritime risk engine
function assessLocally(cargo, port) {
  const w = PORT_WX[port];
  const wet = cargo === "iron_ore" || cargo === "fertilizer";
  let days = 0;
  let level = "LOW / CLEAR BERTHING";
  if (w.cyclone) { days = 4.5; level = "CRITICAL / PORT CLOSURE"; }
  else if (wet && w.rain > 2) { days = Math.ceil((1 + w.rain / 6) * 2) / 2; level = w.rain > 5 ? "CRITICAL / DISCHARGE HALT" : "ELEVATED / DISCHARGE HOLD"; }
  else if (cargo === "coking_coal" && w.rain > 5) { days = 1; level = "ELEVATED / DISCHARGE HOLD"; }
  else if (cargo === "pol_liquid" && w.wind > 25) { days = 1.5; level = "ELEVATED / HOSE DISCONNECT RISK"; }
  return {
    port, data_source: "OFFLINE_DB", wind_speed_knots: w.wind, risk_level: level,
    estimated_delay_days: days, demurrage_exposure_inr: days * DEMURRAGE_PER_DAY,
  };
}

/* ───────────────────────── Helpers ───────────────────────── */

const inr = (n, d = 2) =>
  "₹" + Number(n || 0).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });

const toneOf = (level = "") => (/CRITICAL|CLOSURE/i.test(level) ? "red" : /ELEVATED|HIGH|HOLD/i.test(level) ? "amber" : "green");

const TONES = {
  red: { dark: "bg-red-950 text-red-200 border-red-700", light: "bg-red-50 text-red-800 border-red-300" },
  amber: { dark: "bg-amber-950 text-amber-200 border-amber-700", light: "bg-amber-50 text-amber-900 border-amber-300" },
  green: { dark: "bg-emerald-950 text-emerald-200 border-emerald-700", light: "bg-emerald-50 text-emerald-800 border-emerald-300" },
  blue: { dark: "bg-slate-800 text-sky-200 border-slate-600", light: "bg-sky-50 text-sky-900 border-sky-200" },
};

function buildBriefing(data, cargoId, port) {
  const c = CARGOES.find((x) => x.id === cargoId);
  const m = data.models_diagnostics[cargoId];
  const wx = data.weather_risk_status;
  const price = m.latest_predictions[m.latest_predictions.length - 1];
  const lo = price - m.confidence_interval_half_width;
  const hi = price + m.confidence_interval_half_width;
  const drivers = Object.entries(m.correlations).filter(([k]) => k !== "price_inr_per_tonne").sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  const [dk, dv] = drivers[0] || ["n/a", 0];
  const ceilingMt = c.ceiling ? data.port_capacity_limits[c.ceiling] : data.port_capacity_limits.total_major_ports;
  const critical = /^CRITICAL/.test(m.handling_constraint);

  const bullets = [
    `Expected delivered price for ${c.label} is ${inr(price)} per tonne, with a 95% band of ${inr(lo, 0)} to ${inr(hi, 0)}.`,
    m.is_applicable
      ? `The Ridge model passes its applicability checks (MAPE ${m.mape_percent}%, MAE ${inr(m.mae)}).`
      : `The model is flagged as not applicable (MAPE ${m.mape_percent}%). Treat the forecast as indicative and cross-check against broker quotes.`,
    `Strongest price driver: ${dk.replace(/_/g, " ")} (correlation ${dv > 0 ? "+" : ""}${dv}).`,
    `${port} berthing status is ${wx.risk_level.toLowerCase()} with ${wx.wind_speed_knots} knot winds; estimated delay ${wx.estimated_delay_days} days, demurrage exposure ${inr(wx.demurrage_exposure_inr, 0)}.`,
  ];
  const actions = [
    `Negotiate at or below ${inr(price, 0)}; escalate to the board before committing above ${inr(hi, 0)}.`,
    `Keep planned volumes inside the national handling ceiling of ${ceilingMt.toFixed(1)} MT.`,
    wx.estimated_delay_days > 0
      ? `Defer discharge or reroute, and hold a demurrage contingency of ${inr(wx.demurrage_exposure_inr, 0)}.`
      : `Berthing window is clear; confirm the discharge schedule with the port agent.`,
    critical
      ? "Brief the stevedoring team on the cargo's weather stop-work trigger before arrival."
      : "Maintain standard stacking and covering procedures at the discharge berth.",
  ];
  return { title: `Procurement advisory: ${c.label} via ${port}`, bullets, actions };
}

/* ───────────────────────── Component ───────────────────────── */

export default function SailLogisticsTerminal() {
  const [data, setData] = useState(DEFAULT_DATA);
  const [status, setStatus] = useState("connecting"); // connecting | live | offline
  const [dark, setDark] = useState(true);
  const [cargo, setCargo] = useState(DEFAULT_DATA.active_frontend_cargo);
  const [port, setPort] = useState(DEFAULT_DATA.weather_risk_status.port);
  const [synced, setSynced] = useState({ cargo: DEFAULT_DATA.active_frontend_cargo, port: DEFAULT_DATA.weather_risk_status.port });
  const [busy, setBusy] = useState(false);
  const [chartOpen, setChartOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    api.getDashboard()
      .then((d) => {
        if (!alive) return;
        const merged = { ...DEFAULT_DATA, ...d };
        setData(merged);
        setCargo(merged.active_frontend_cargo);
        setPort(merged.weather_risk_status.port);
        setSynced({ cargo: merged.active_frontend_cargo, port: merged.weather_risk_status.port });
        setStatus("live");
      })
      .catch(() => alive && setStatus("offline"));
    return () => { alive = false; };
  }, []);

  const sync = useCallback(async () => {
    setBusy(true);
    try {
      const d = await api.simulate({ cargo, port });
      setData((p) => ({ ...p, ...d }));
      setStatus("live");
    } catch {
      setData((p) => ({ ...p, active_frontend_cargo: cargo, weather_risk_status: assessLocally(cargo, port), active_graph_base64: null }));
      setStatus("offline");
    }
    setSynced({ cargo, port });
    setBusy(false);
  }, [cargo, port]);

  const m = data.models_diagnostics[cargo];
  const wx = data.weather_risk_status;
  const cargoMeta = CARGOES.find((c) => c.id === cargo);
  const price = m.latest_predictions[m.latest_predictions.length - 1];
  const lo = price - m.confidence_interval_half_width;
  const hi = price + m.confidence_interval_half_width;
  const ceilingMt = cargoMeta.ceiling ? data.port_capacity_limits[cargoMeta.ceiling] : null;
  const critical = /^CRITICAL/.test(m.handling_constraint);
  const pending = synced.cargo !== cargo || synced.port !== port;
  const source = status === "live" ? wx.data_source : "OFFLINE_DB";
  const briefing = useMemo(() => buildBriefing(data, cargo, wx.port), [data, cargo, wx.port]);
  const remoteBrief = typeof data.executive_briefing === "string" ? data.executive_briefing.split("\n").filter(Boolean) : null;

  const mode = dark ? "dark" : "light";
  const T = dark
    ? { page: "bg-slate-950 text-slate-100", panel: "bg-slate-900 border-slate-800", muted: "text-slate-400", inset: "bg-slate-800/60 border-slate-700", rule: "border-slate-800" }
    : { page: "bg-slate-100 text-slate-900", panel: "bg-white border-slate-200", muted: "text-slate-500", inset: "bg-slate-50 border-slate-200", rule: "border-slate-200" };
  const badge = (tone) => `inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-xs font-semibold ${TONES[tone][mode]}`;
  const focus = "focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400";

  return (
    <div className={`min-h-screen ${T.page}`} style={{ fontFamily: "ui-sans-serif, system-ui, 'Segoe UI', Roboto, sans-serif" }}>
      {/* ── Enterprise header ── */}
      <header style={{ backgroundColor: NAVY }} className="text-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6">
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded text-lg font-bold tracking-tight" style={{ backgroundColor: BLUE }} aria-hidden="true">
              SAIL
            </div>
            <div>
              <p className="text-sm font-semibold">Steel Authority of India Limited <span className="font-normal text-sky-200">(Maharatna CPSE)</span></p>
              <h1 className="text-lg font-bold leading-tight sm:text-xl">Autonomous Logistics &amp; Strategic Raw Materials Terminal</h1>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded border border-emerald-400 bg-emerald-950 px-2 py-1 text-xs font-semibold text-emerald-200">
              <span className="h-2 w-2 rounded-full bg-emerald-400" />{data.system_status}
            </span>
            <span className="inline-flex items-center gap-1.5 rounded border border-sky-300 bg-white/10 px-2 py-1 text-xs font-semibold">
              {source === "OFFLINE_DB" ? <WifiOff size={13} /> : <Wifi size={13} />}{status === "connecting" ? "CONNECTING" : source}
            </span>
            <button onClick={() => setDark(!dark)} aria-label="Toggle light or dark theme" className={`rounded border border-sky-300 p-1.5 hover:bg-white/10 ${focus}`}>
              {dark ? <Sun size={16} /> : <Moon size={16} />}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-5 px-4 py-5 sm:px-6">
        {/* ── Control bar ── */}
        <section className={`rounded-lg border p-4 ${T.panel}`} aria-label="Controls">
          <h2 className="mb-2 text-sm font-semibold">Commodity payload</h2>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {CARGOES.map(({ id, label, sub, Icon }) => {
              const on = id === cargo;
              return (
                <button
                  key={id} onClick={() => setCargo(id)} aria-pressed={on}
                  className={`flex items-start gap-3 rounded-lg border-2 p-3 text-left transition-colors ${focus} ${on ? "text-white" : T.inset}`}
                  style={on ? { backgroundColor: BLUE, borderColor: "#38bdf8" } : undefined}
                >
                  <Icon size={22} className="mt-0.5 shrink-0" />
                  <span>
                    <span className="block text-sm font-semibold">{label}</span>
                    <span className={`block text-xs ${on ? "text-sky-100" : T.muted}`}>{sub}</span>
                  </span>
                </button>
              );
            })}
          </div>

          <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
            <div>
              <h2 className="mb-2 text-sm font-semibold">Discharge port</h2>
              <div className="flex flex-wrap gap-2" role="group" aria-label="Discharge port">
                {PORTS.map((p) => {
                  const on = p === port;
                  return (
                    <button
                      key={p} onClick={() => setPort(p)} aria-pressed={on}
                      className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm ${focus} ${on ? "border-sky-400 font-semibold text-white" : T.inset}`}
                      style={on ? { backgroundColor: NAVY } : undefined}
                    >
                      <Anchor size={13} />{p}
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="flex items-center gap-3">
              {pending && <span className={badge("amber")}>Selection not synced</span>}
              <button
                onClick={sync} disabled={busy}
                className={`inline-flex items-center gap-2 rounded px-4 py-2 text-sm font-semibold text-white disabled:opacity-60 ${focus}`}
                style={{ backgroundColor: BLUE }}
              >
                <RefreshCw size={16} className={busy ? "animate-spin" : ""} />{busy ? "Syncing…" : "Simulate and sync"}
              </button>
            </div>
          </div>
        </section>

        {/* ── Critical alert banner ── */}
        <section
          role="alert"
          className={`flex flex-wrap items-start gap-4 rounded-lg border-l-8 border p-4 ${critical ? TONES.red[mode] : TONES.amber[mode]}`}
        >
          <AlertTriangle size={30} className="shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="text-base font-bold">{critical ? "Critical handling constraint" : "Handling advisory"}: {cargoMeta.label}</p>
            <p className="mt-1 max-w-3xl text-sm">{m.handling_constraint}</p>
          </div>
          <div className={`rounded border px-3 py-2 text-sm ${dark ? "border-current/40" : "border-current/40"}`}>
            <span className="flex items-center gap-1.5 font-semibold"><ShieldCheck size={15} />National handling ceiling</span>
            <span className="mt-0.5 block text-base font-bold">
              {ceilingMt !== null ? `${ceilingMt.toFixed(1)} MT` : `${data.port_capacity_limits.total_major_ports.toFixed(2)} MT`}
            </span>
            {ceilingMt === null && <span className="block text-xs">All major ports combined</span>}
          </div>
        </section>

        {/* ── KPI grid ── */}
        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Key metrics">
          <article className={`rounded-lg border p-4 ${T.panel}`}>
            <p className={`flex items-center gap-2 text-sm ${T.muted}`}><TrendingDown size={16} />Target delivered spot price</p>
            <p className="mt-2 text-2xl font-bold tabular-nums">{inr(price)}<span className={`text-sm font-normal ${T.muted}`}> / tonne</span></p>
            <div className="mt-3 flex flex-wrap gap-2">
              <span className={badge("blue")}>±{inr(m.mae)} MAE</span>
              <span className={badge(m.is_applicable ? "green" : "amber")}>
                MAPE {m.mape_percent}%{m.is_applicable ? "" : " · low reliability"}
              </span>
            </div>
          </article>

          <article className={`rounded-lg border p-4 ${T.panel}`}>
            <p className={`flex items-center gap-2 text-sm ${T.muted}`}><BarChart3 size={16} />Volatility risk band (95% CI)</p>
            <p className="mt-2 text-xl font-bold tabular-nums">{inr(lo, 0)} – {inr(hi, 0)}</p>
            <div className={`relative mt-4 h-2 rounded-full ${dark ? "bg-slate-700" : "bg-slate-200"}`} aria-hidden="true">
              <div className="absolute inset-y-0 left-0 right-0 rounded-full" style={{ backgroundColor: BLUE, opacity: 0.55 }} />
              <div className="absolute -top-1 h-4 w-1 rounded bg-sky-400" style={{ left: "50%" }} />
            </div>
            <div className={`mt-1 flex justify-between text-xs ${T.muted}`}><span>Floor</span><span>Ceiling</span></div>
          </article>

          <article className={`rounded-lg border p-4 ${T.panel}`}>
            <p className={`flex items-center gap-2 text-sm ${T.muted}`}><Anchor size={16} />Demurrage exposure surcharge</p>
            <p className="mt-2 text-2xl font-bold tabular-nums">{inr(wx.demurrage_exposure_inr)}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <span className={badge(wx.estimated_delay_days > 0 ? "amber" : "green")}>{wx.estimated_delay_days} days est. berthing delay</span>
            </div>
            <p className={`mt-2 text-xs ${T.muted}`}>Rate: {inr(DEMURRAGE_PER_DAY, 0)} per Panamax day</p>
          </article>

          <article className={`rounded-lg border p-4 ${T.panel}`}>
            <p className={`flex items-center gap-2 text-sm ${T.muted}`}><Wind size={16} />Meteorological status</p>
            <p className="mt-2 text-2xl font-bold">{wx.port}</p>
            <p className="text-sm tabular-nums">{wx.wind_speed_knots} knots surface wind</p>
            <div className={`mt-2 h-1.5 rounded-full ${dark ? "bg-slate-700" : "bg-slate-200"}`} aria-hidden="true">
              <div className={`h-full rounded-full ${wx.wind_speed_knots > 25 ? "bg-red-500" : "bg-sky-400"}`} style={{ width: `${Math.min(100, (wx.wind_speed_knots / 40) * 100)}%` }} />
            </div>
            <div className="mt-3"><span className={badge(toneOf(wx.risk_level))}>{wx.risk_level}</span></div>
          </article>
        </section>

        {/* ── Executive briefing ── */}
        <section className={`rounded-lg border ${T.panel}`} aria-label="AI strategic executive briefing">
          <div className={`flex flex-wrap items-center justify-between gap-2 border-b px-5 py-3 ${T.rule}`}>
            <h2 className="flex items-center gap-2 font-semibold"><FileText size={18} />AI strategic executive briefing</h2>
            <span className={badge("blue")}>{remoteBrief ? "Gemini advisor" : "Generated from model diagnostics"}</span>
          </div>
          <article className="max-w-4xl px-5 py-4" style={{ fontFamily: "Georgia, 'Times New Roman', serif" }}>
            <p className={`text-xs ${T.muted}`}>To: Procurement Desk and Board &nbsp;|&nbsp; Re: {briefing.title}</p>
            {remoteBrief ? (
              <div className="mt-3 space-y-2 leading-relaxed">{remoteBrief.map((l, i) => <p key={i}>{l}</p>)}</div>
            ) : (
              <>
                <h3 className="mt-3 font-bold">Situation</h3>
                <ul className="mt-1 list-disc space-y-1 pl-5 leading-relaxed">
                  {briefing.bullets.map((b, i) => <li key={i}>{b}</li>)}
                </ul>
                <h3 className="mt-4 font-bold">Recommended actions</h3>
                <ul className="mt-1 space-y-1.5 leading-relaxed">
                  {briefing.actions.map((a, i) => (
                    <li key={i} className="flex gap-2"><ShieldCheck size={16} className="mt-1 shrink-0 text-emerald-500" /><span>{a}</span></li>
                  ))}
                </ul>
              </>
            )}
          </article>
        </section>

        {/* ── Chart viewer ── */}
        <section className={`rounded-lg border ${T.panel}`}>
          <button
            onClick={() => setChartOpen(!chartOpen)} aria-expanded={chartOpen}
            className={`flex w-full items-center justify-between gap-3 px-5 py-3 text-left font-semibold ${focus}`}
          >
            <span className="flex items-center gap-2"><BarChart3 size={18} />View econometric trajectory &amp; risk forecast graph</span>
            <ChevronDown size={18} className={`transition-transform ${chartOpen ? "rotate-180" : ""}`} />
          </button>
          {chartOpen && (
            <div className={`border-t p-4 ${T.rule}`}>
              {data.active_graph_base64 ? (
                <img src={data.active_graph_base64} alt="Predictive Price Trajectory" className="mx-auto h-auto max-w-full rounded" />
              ) : (
                <div className={`rounded border p-3 ${T.inset}`}>
                  <p className={`mb-2 text-sm ${T.muted}`}>
                    {busy ? "Rendering trajectory from the backend…" : "Backend graph not available. Illustrative curve shown; run a sync with Flask online for the real forecast."}
                  </p>
                  <svg viewBox="0 0 600 220" className="h-auto w-full" role="img" aria-label="Illustrative price trajectory with confidence band">
                    <polygon points="30,150 130,128 230,138 330,100 430,84 530,62 530,126 430,140 330,150 230,176 130,172 30,180" fill={BLUE} opacity="0.25" />
                    <polyline points="30,165 130,150 230,157 330,125 430,112 530,94" fill="none" stroke="#38bdf8" strokeWidth="3" strokeLinejoin="round" />
                    <line x1="30" y1="200" x2="570" y2="200" stroke="#64748b" />
                    <line x1="30" y1="20" x2="30" y2="200" stroke="#64748b" />
                    <text x="36" y="16" fontSize="11" fill="#94a3b8">INR / tonne</text>
                    <text x="500" y="216" fontSize="11" fill="#94a3b8">Forecast horizon</text>
                  </svg>
                </div>
              )}
            </div>
          )}
        </section>

        <footer className={`pb-4 text-xs ${T.muted}`}>
          Source: Ridge econometric engine V2, maritime risk engine V3, Ministry of Ports handling ceilings. Status: {status}.
        </footer>
      </main>
    </div>
  );
}