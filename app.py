import json
import os
import re
from datetime import date, timedelta
from difflib import SequenceMatcher

import pandas as pd
import streamlit as st
from lead_finder import qualify_leads, search_places

st.set_page_config(page_title="AI Lead Finder — Pro", page_icon="🎯", layout="wide")
CRM_FILE = "crm_leads.json"
STATUSES = ["New", "Contacted", "Replied", "Interested", "Call booked", "Client", "Rejected"]


def load_crm():
    if not os.path.exists(CRM_FILE): return {}
    try:
        with open(CRM_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except Exception: return {}


def save_crm(data):
    with open(CRM_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)


def norm(s): return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def dedupe(leads):
    out, domains, names = [], set(), []
    for x in leads:
        name = norm(x.get("business_name")); domain = norm((x.get("website") or "").split("//")[-1].split("/")[0].removeprefix("www."))
        if domain and domain in domains: continue
        if name and any(SequenceMatcher(None, name, old).ratio() >= .90 for old in names): continue
        if domain: domains.add(domain)
        names.append(name); out.append(x)
    return out


def competitor_signals(x):
    text = json.dumps(x, ensure_ascii=False).lower()
    terms = ["bookkeeping", "bookkeeper", "accounting firm", "accountant", "outsourced finance", "fractional cfo"]
    return [t for t in terms if t in text]


def channel(x):
    if x.get("public_emails"): return "Email", "Public business email available"
    if x.get("linkedin") and x.get("decision_maker_evidence"): return "LinkedIn", "Public LinkedIn plus decision-maker evidence"
    if x.get("whatsapp"): return "WhatsApp", "Public WhatsApp link available"
    if x.get("instagram") or x.get("facebook"): return "Social DM", "Public social profile available"
    if x.get("public_phones"): return "Phone", "Public business phone available"
    return "Research", "No strong public channel found"


def first_line(x):
    name = x.get("business_name", "your business"); pain = (x.get("potential_pain_points") or [""])[0]
    return f"I came across {name} and noticed a potential area where finance/admin work may be taking time." if pain else f"I came across {name} while researching businesses in your market."


def enrich_ui_fields(leads):
    for x in leads:
        signals = competitor_signals(x); x["competitor_signals"] = signals; x["existing_accounting_support"] = bool(signals)
        ch, why = channel(x); x["recommended_channel"] = ch; x["channel_reason"] = why; x["personalized_first_line"] = first_line(x)
        x["contactability_score"] = 100 if x.get("public_emails") else 75 if x.get("public_phones") else 55 if any(x.get(k) for k in ("linkedin", "instagram", "facebook", "whatsapp")) else 10
        x["decision_maker_score"] = 100 if x.get("decision_maker_evidence") else 40
        x["business_fit_score"] = min(100, 60 + (15 if x.get("website") else 0) + (10 if x.get("public_emails") else 0))
        x["potential_need_score"] = min(100, 55 + (15 if any(k in json.dumps(x, ensure_ascii=False).lower() for k in ("shopify", "stripe", "ecommerce", "multiple locations", "agency")) else 0) + (10 if x.get("website") and x.get("public_emails") else 0))
    return leads


def market_score(country, industry, price):
    language = {"Australia":25,"United Kingdom":24,"Canada":23,"Singapore":25,"United States":24,"New Zealand":22,"UAE":20,"Malaysia":18}; fit = {"Digital agency":25,"Marketing agency":25,"Consultant":24,"E-commerce":24,"Property management":22,"Cleaning company":21,"Restaurant":18,"Salon":17,"Contractor":20}; affordability = {"Australia":25,"United States":25,"Singapore":25,"United Kingdom":23,"Canada":23,"UAE":24,"New Zealand":21,"Malaysia":16}
    return min(100, language.get(country,18) + fit.get(industry,20) + affordability.get(country,20) + max(0,min(25,int(price/8))))


crm = load_crm()
st.title("🎯 AI Lead Finder — Pro")
st.caption("Public-web lead research + qualification + outreach planning + CRM. No login bypassing or private-data scraping.")
tab_find, tab_crm, tab_analytics, tab_market = st.tabs(["🔎 Find Leads", "📋 CRM / Follow-ups", "📈 Analytics", "🌍 Market Discovery"])

with tab_find:
    with st.sidebar:
        st.header("Search")
        location = st.text_input("Location", "Kuala Lumpur, Malaysia")
        business_type = st.text_input("Business type", "digital agencies")
        service = st.text_input("Service you sell", "basic bookkeeping")
        ideal_customer = st.text_area("Ideal customer", "Small owner-managed businesses that may benefit from recurring bookkeeping, reconciliation, Excel cleanup, or simple monthly reports.", height=110)
        count = st.slider("Businesses to return", 5, 50, 15)
        model = st.text_input("Local Ollama model", "qwen3:4b")
        st.divider(); st.subheader("Speed / quality")
        enrich = st.checkbox("Public-web enrichment", True)
        deep_research = st.checkbox("Deep decision-maker + social research", False, help="OFF = much faster. Turn ON only after the fast scan finds promising leads.")
        require_contact = st.checkbox("Remove leads with no public contact/profile", True)
        require_website = st.checkbox("Remove leads with no public website", False)
        crawl_pages = st.slider("Pages per website", 1, 5, 2, help="2 is the fast default. Use 3–5 for deeper research.")
        hide_competitors = st.checkbox("Remove leads with existing accounting/bookkeeping signals", False)
        run = st.button("Find leads", type="primary", use_container_width=True)

    if run:
        with st.status("Finding and qualifying businesses...", expanded=True) as status:
            try:
                st.write("1/4 — Finding candidate businesses")
                places = dedupe(search_places(location, business_type, min(count * 2, 30) if enrich else count))
                st.write(f"Found {len(places)} candidates after duplicate filtering. Research cap: 30.")
                if not places: status.update(label="No businesses found", state="error"); st.stop()
                st.write("2/4 — Fast discovery mode: web search + website checks run in parallel")
                progress = st.progress(0, text="Starting enrichment...")
                def on_progress(done, total):
                    progress.progress(done / total, text=f"Researching public data: {done}/{total} candidates")
                st.write(f"3/4 — Up to {crawl_pages} pages per website; deep research={'ON' if deep_research else 'OFF'}")
                leads = qualify_leads(places, service, ideal_customer, model, enrich=enrich, location=location, require_contact=require_contact, require_website=require_website, crawl_pages=crawl_pages, progress_callback=on_progress, deep=deep_research)
                progress.empty()
                leads = enrich_ui_fields(leads)
                if hide_competitors: leads = [x for x in leads if not x.get("existing_accounting_support")]
                leads = leads[:count]
                st.write(f"4/4 — {len(leads)} usable leads remain")
                status.update(label=f"Done — {len(leads)} leads", state="complete")
                st.session_state["leads"] = leads
            except Exception as exc:
                status.update(label="Search failed", state="error"); st.exception(exc); st.stop()

    leads = st.session_state.get("leads", [])
    if leads:
        st.subheader(f"Qualified leads ({len(leads)})")
        min_score = st.slider("Minimum lead score", 0, 100, 60)
        for i, lead in enumerate([x for x in leads if x.get("score",0) >= min_score], 1):
            score = lead.get("score",0); icon = "🔥" if score >= 80 else "🟡" if score >= 60 else "⚪"
            with st.expander(f"{i}. {lead.get('business_name','Unknown')} — {score}/100 {icon} — {lead.get('recommended_channel','Research')}"):
                a,b,c = st.columns(3)
                with a:
                    st.write(f"**Website:** {lead.get('website') or 'Not found'}"); st.write(f"**Email:** {', '.join(lead.get('public_emails',[])) or 'Not found'}"); st.write(f"**Phone:** {', '.join(lead.get('public_phones',[])) or 'Not found'}"); st.write(f"**Decision-maker evidence:** {'Yes' if lead.get('decision_maker_evidence') else 'Not found'}")
                with b:
                    st.write(f"**Fit:** {lead.get('business_fit_score',0)}/100"); st.write(f"**Potential need:** {lead.get('potential_need_score',0)}/100"); st.write(f"**Contactability:** {lead.get('contactability_score',0)}/100"); st.write(f"**Decision maker:** {lead.get('decision_maker_score',0)}/100")
                with c:
                    st.write(f"**Best channel:** {lead.get('recommended_channel')}"); st.write(f"**Why:** {lead.get('channel_reason')}"); st.write(f"**Competitor signals:** {', '.join(lead.get('competitor_signals',[])) or 'None detected'}")
                st.write("**Personalized first line:**", lead.get("personalized_first_line", "")); st.write("**AI outreach draft:**"); st.code(lead.get("outreach", ""), language=None)
                if lead.get("decision_maker_evidence"):
                    with st.expander("Decision-maker evidence to verify"):
                        for item in lead["decision_maker_evidence"][:5]: st.caption(item)
                if lead.get("google_maps"): st.markdown(f"[Open in Google Maps]({lead['google_maps']})")
                if lead.get("contact_page"): st.markdown(f"[Open contact page]({lead['contact_page']})")
                if lead.get("search_sources"):
                    with st.expander("Public sources used"):
                        for src in lead["search_sources"]: st.write(src)
                if st.button("Save to CRM", key="save_" + norm(lead.get("business_name"))):
                    key = lead.get("website") or lead.get("business_name"); crm[key] = {**lead, "status":"New", "created":str(date.today()), "next_follow_up":str(date.today()+timedelta(days=3)), "notes":""}; save_crm(crm); st.success("Saved to CRM")
        export = pd.DataFrame(leads)
        for col in ["reasons","unknowns","public_emails","public_phones","decision_maker_evidence","website_pages","search_sources","competitor_signals"]:
            if col in export: export[col] = export[col].apply(lambda x: " | ".join(map(str,x)) if isinstance(x,list) else x)
        st.download_button("Download enriched leads CSV", export.to_csv(index=False).encode("utf-8"), "ai_enriched_leads.csv", "text/csv")
    else: st.info("Set your criteria and click Find leads.")

with tab_crm:
    if not crm: st.info("Save leads from Find Leads to start your CRM.")
    else:
        st.subheader("Pipeline")
        for key, lead in list(crm.items()):
            with st.expander(f"{lead.get('business_name',key)} — {lead.get('status','New')}"):
                current=lead.get("status","New"); status=st.selectbox("Status",STATUSES,index=STATUSES.index(current) if current in STATUSES else 0,key="status_"+norm(key)); default=date.fromisoformat(lead["next_follow_up"]) if lead.get("next_follow_up") else date.today()+timedelta(days=3); follow=st.date_input("Next follow-up",value=default,key="follow_"+norm(key)); notes=st.text_area("Notes",lead.get("notes",""),key="notes_"+norm(key)); st.write(f"**Best channel:** {lead.get('recommended_channel','Research')}")
                if status in ("Contacted","Replied","Interested") and follow <= date.today(): st.warning("Follow-up is due.")
                if st.button("Update",key="upd_"+norm(key)): lead.update({"status":status,"next_follow_up":str(follow),"notes":notes});crm[key]=lead;save_crm(crm);st.rerun()

with tab_analytics:
    if not crm: st.info("Save leads to see analytics.")
    else:
        df=pd.DataFrame(list(crm.values()));st.metric("Total leads",len(df));cols=st.columns(len(STATUSES))
        for col,status in zip(cols,STATUSES):col.metric(status,int((df.get("status")==status).sum()) if "status" in df else 0)
        if "status" in df:st.bar_chart(df["status"].value_counts())
        if "score" in df:st.metric("Average score",round(pd.to_numeric(df["score"],errors="coerce").mean(),1))
        if "recommended_channel" in df:st.subheader("Channel mix");st.bar_chart(df["recommended_channel"].value_counts())
        if "business_type" in df:st.subheader("Industry mix");st.bar_chart(df["business_type"].value_counts())
        st.download_button("Download CRM CSV",df.to_csv(index=False),"ailead_crm.csv","text/csv")

with tab_market:
    st.subheader("🌍 Market Discovery");st.caption("Transparent testing heuristic; not a factual market-size or wealth claim.")
    countries=st.multiselect("Markets",["Australia","Singapore","United Kingdom","Canada","United States","UAE","New Zealand","Malaysia"],["Australia","Singapore","United Kingdom","Canada"]);industries=st.multiselect("Industries",["Digital agency","Marketing agency","Consultant","E-commerce","Property management","Cleaning company","Restaurant","Salon","Contractor"],["Digital agency","Consultant","E-commerce"]);price=st.number_input("Target monthly price (USD)",50,1000,175,25)
    if countries and industries:
        rows=[{"Country":c,"Industry":i,"Priority score":market_score(c,i,price)} for c in countries for i in industries];st.dataframe(pd.DataFrame(rows).sort_values("Priority score",ascending=False),use_container_width=True,hide_index=True)
