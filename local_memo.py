"""Offline CFO briefing, built only from the optimizer result.

Used when the Gemini API is unavailable (quota, no key, network). Works for every
cargo, origin and port because it reads everything from the result dict, and it
degrades gracefully when a field (for example the date plan) is missing.
Returns the same HTML subset the dashboard renders: h3, p, ul, li, strong, em.
"""
import html as _html

HANDLING = {
    "coal": "Keep the stack dry: wet coking coal carries a spontaneous-combustion risk.",
    "iron": "Halt discharge in heavy rain: wet iron ore fines can liquefy.",
    "fert": "Keep the cargo dry: rain during discharge can dissolve water-soluble fertilizer.",
    "pol": "Watch surface winds: above 25 knots the marine hoses must disconnect.",
}
EVENTS = {
    "none": "no disruption",
    "war": "geopolitical tension",
    "weather_issues": "a monsoon / weather alert",
    "port_closed": "port congestion",
    "industry_needs_rise": "an industry demand surge",
    "disaster": "a disaster",
}


def local_cfo_memo(d):
    esc = lambda x: _html.escape(str(x))
    crore = lambda x: f"₹{x / 1e7:.2f} crore"
    d = d or {}
    fa = d.get("financial_analysis") or {}
    t = d.get("timing") or {}
    a = d.get("scenario_a_buy_now") or {}
    b = d.get("scenario_b_wait") or {}

    cargo = d.get("cargo_type") or "the cargo"
    origin, port = d.get("origin"), d.get("port")
    event = EVENTS.get(d.get("event_keyword", "none"), "a market disruption")
    strategy = str(fa.get("cheapest_option", "WAIT")).replace("_", " ")
    route = (f" from {esc(origin)}" if origin else "") + (f" to {esc(port)}" if port else "")

    # 1. Verdict
    verdict = f"Execute <strong>{esc(strategy)}</strong> for {esc(cargo)}{route}."
    w = t.get("order_window")
    if w:
        verdict += f" Suggested order window: <strong>{esc(w['start'])} to {esc(w['end'])}</strong>."
    if t and t.get("feasible") is False:
        verdict = (f"The delivery date cannot be met for {esc(cargo)}{route}: the earliest arrival is "
                   f"<strong>{esc(t.get('earliest_arrival', 'n/a'))}</strong>. Order immediately or choose a closer origin.")
    rec = d.get("recommended_origin")
    if rec and origin and rec != origin:
        verdict += f" The model recommends sourcing from <strong>{esc(rec)}</strong> instead."

    # 2. Margin
    saving = fa.get("savings")
    pct = fa.get("margin_percent")
    if saving is None and a.get("total_cost") is not None and b.get("total_cost") is not None:
        saving = abs(a["total_cost"] - b["total_cost"])
        pct = saving / max(a["total_cost"], b["total_cost"]) * 100
    margin = (f"This choice saves <strong>{crore(saving)}</strong>" + (f" ({pct:.2f}%)" if pct is not None else "") +
              " versus the alternative strategy." if saving is not None else "No saving figure is available for this scenario.")

    infeasible = t.get("feasible") is False
    if infeasible:
        margin = "No saving is calculated because the delivery date cannot be met from this origin."

    # 3. Math
    parts = []
    if a.get("godown_storage_cost") is not None:
        parts.append(f"godown storage if bought now: {crore(a['godown_storage_cost'])}")
    dem = (b.get("logistics") or {}).get("demurrage_penalty")
    if dem is not None:
        parts.append(f"demurrage if waiting: {crore(dem)}")
    base, shock = b.get("predicted_base_material_cost"), b.get("shock_material_cost")
    if base is not None and shock is not None:
        parts.append(f"market shock on materials ({esc(event)}): {crore(shock - base)}")
    math = "; ".join(parts) + "." if parts and not infeasible else "Cost components are in the audit panel."
    reasons = "".join(f"<li>{esc(r)}</li>" for r in (d.get("origin_reasons") or [])[:3])

    # 4. Risk: shock 20% more severe than assumed
    extra = (shock - base) * 0.2 if base is not None and shock is not None and not infeasible else None
    risk = (f"If the disruption is 20% more severe, material cost rises by a further <strong>{crore(extra)}</strong> "
            f"under the waiting strategy." if extra is not None else "Exposure is not quantified for this scenario; monitor the disruption closely.")
    key = next((k for k in HANDLING if k in str(cargo).lower()), None)
    handling = f" {HANDLING[key]}" if key else ""

    sm = d.get("scenario_matrix") or {}
    tot = sm.get("totals") or {}
    extra_html = ""
    if tot and sm.get("provided"):
        extra_html += (f"<p>The extra charges entered add <strong>{sm['extras_pct']:.1f}%</strong> of the predicted cost "
                       f"({crore(sm['extras_amount'])}). Estimated cost range: {crore(tot['no_disruption'])} (no disruption) to "
                       f"<strong>{crore(tot['combined'])}</strong> (all risks and charges).</p>")
    missing = d.get("inputs_not_provided") or []
    if missing:
        extra_html += ("<p><em>Not included in this estimate (not provided): " + esc("; ".join(missing)) +
                       ". Enter them in the 'Improve this estimate' panel and recalculate for a fuller picture.</em></p>")

    return (
        "<p><em>Local engine briefing: the AI service is unavailable, so this was generated directly from the cost model.</em></p>"
        f"<h3>1. THE VERDICT &amp; TIMELINE</h3><p>{verdict}</p>"
        f"<h3>2. MARGIN ANALYSIS</h3><p>{margin}</p>"
        f"<h3>3. THE MATH JUSTIFICATION</h3><p>{math}</p>" + (f"<ul>{reasons}</ul>" if reasons else "") +
        f"<h3>4. ALTERNATIVE RISK</h3><p>{risk}{esc(handling)}</p>" + extra_html
    )