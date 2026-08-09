import json
import os
import re
from datetime import date
from typing import Any

import requests

from lead_finder import enrich_lead, _deterministic_score

OLLAMA_URL = "http://localhost:11434/api/generate"
CRM_FILE = "crm_leads.json"


def _heuristic_scores(b: dict[str, Any], service: str, ideal_customer: str) -> dict[str, int]:
    text = json.dumps(b, ensure_ascii=False).lower()
    contact = 100 if b.get("public_emails") else 75 if b.get("public_phones") else 55 if any(b.get(k) for k in ("linkedin", "instagram", "facebook", "whatsapp")) else 10
    dm = 100 if b.get("decision_makers") else 60 if b.get("decision_maker_evidence") else 15
    fit = 60
    for word in re.findall(r"[a-zA-Z]{4,}", (service + " " + ideal_customer).lower()):
        if word in text:
            fit = min(100, fit + 4)
    need = 55
    if any(x in text for x in ("shopify", "stripe", "ecommerce", "multiple locations", "services", "booking", "online store", "agency")):
        need += 15
    if b.get("public_emails") and b.get("website"):
        need += 10
    return {"contactability_score": min(contact, 100), "decision_maker_score": min(dm, 100), "business_fit_score": min(fit, 100), "potential_need_score": min(need, 100)}


def _ai_score(b: dict[str, Any], service: str, ideal_customer: str, model: str) -> dict[str, Any]:
    prompt = f'''You are a careful B2B lead qualification assistant.
SERVICE: {service}
IDEAL CUSTOMER: {ideal_customer}
PUBLIC BUSINESS DATA ONLY:
{json.dumps(b, ensure_ascii=False, indent=2)}

Return ONLY JSON with these keys:
score, contactability_score, decision_maker_score, business_fit_score, potential_need_score, fit, decision_maker, pain_points, reasons, recommended_channel, outreach_email, outreach_linkedin, outreach_dm, unknowns.
Rules: scores 0-100; never invent a person's name, revenue, employee count, need, or contact. decision_maker must be an empty string unless supported by public evidence. pain_points must be framed as potential and evidence-based. Keep each outreach under 700 characters.'''
    r = requests.post(OLLAMA_URL, json={"model": model, "prompt": prompt, "stream": False, "format": "json"}, timeout=120)
    r.raise_for_status()
    x = json.loads(r.json().get("response", "{}"))
    for k in ("score", "contactability_score", "decision_maker_score", "business_fit_score", "potential_need_score"):
        x[k] = max(0, min(100, int(x.get(k, 0))))
    for k, v in {"fit":"low", "decision_maker":"", "pain_points":[], "reasons":[], "recommended_channel":"Email", "outreach_email":"", "outreach_linkedin":"", "outreach_dm":"", "unknowns":[]}.items():
        x.setdefault(k, v)
    return x


def qualify_pro(raw: dict[str, Any], location: str, service: str, ideal_customer: str, model: str = "qwen3:4b", crawl_pages: int = 5) -> dict[str, Any]:
    b = enrich_lead(dict(raw), location, crawl_pages)
    try:
        score = _ai_score(b, service, ideal_customer, model)
        mode = "Local AI"
    except Exception:
        s = _heuristic_scores(b, service, ideal_customer)
        score = {**s, "score": round(sum(s.values()) / 4), "fit": "high" if sum(s.values())/4 >= 75 else "medium" if sum(s.values())/4 >= 60 else "low", "decision_maker": (b.get("decision_makers") or [{}])[0].get("name", ""), "pain_points":["Potential bookkeeping/admin workload based on public signals; verify before outreach."], "reasons":["Public business listing found", "Public contact evidence found"], "recommended_channel":"Email" if b.get("public_emails") else "LinkedIn" if b.get("linkedin") else "Phone", "outreach_email":f"Hi! I came across {b['business_name']}. I help small businesses with bookkeeping, reconciliation and simple monthly financial reporting. Would a quick chat about your current setup be useful?", "outreach_linkedin":"Hi! I came across your business and help small businesses with bookkeeping and monthly financial admin. Open to a quick chat?", "outreach_dm":"Hi! I came across your business and wanted to ask if you currently have bookkeeping support in place.", "unknowns":["Business size", "Current bookkeeping setup", "Whether support is needed"]}
        mode = "Rule-based fallback"
    return {**b, **score, "ai_mode": mode, "crm_status": "New", "last_contacted": "", "next_follow_up": "", "notes": ""}


def load_crm() -> list[dict[str, Any]]:
    if not os.path.exists(CRM_FILE):
        return []
    try:
        with open(CRM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def save_crm(records: list[dict[str, Any]]) -> None:
    with open(CRM_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def upsert_crm(lead: dict[str, Any], status: str, notes: str = "", follow_up: str = "") -> None:
    records = load_crm(); key = lead.get("business_name", "").strip().lower(); found = next((r for r in records if r.get("business_name", "").strip().lower() == key), None)
    payload = {"business_name": lead.get("business_name", ""), "website": lead.get("website", ""), "email": (lead.get("public_emails") or [""])[0], "phone": (lead.get("public_phones") or [""])[0], "linkedin": lead.get("linkedin", ""), "decision_maker": lead.get("decision_maker", ""), "score": lead.get("score", 0), "status": status, "last_contacted": date.today().isoformat() if status == "Contacted" else (found or {}).get("last_contacted", ""), "next_follow_up": follow_up, "notes": notes}
    if found: found.update(payload)
    else: records.append(payload)
    save_crm(records)
