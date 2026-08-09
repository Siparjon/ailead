import json
import pandas as pd
import streamlit as st
from lead_finder import qualify_leads, search_places

st.set_page_config(page_title="AI Lead Finder — Free", page_icon="🎯", layout="wide")
st.title("🎯 AI Lead Finder — Free")
st.caption("Public-web lead research: places + websites + public contacts + public social/professional profiles + bounded site crawl + local AI. No paid API keys.")

with st.sidebar:
    st.header("Search")
    location = st.text_input("Location", "Kuala Lumpur, Malaysia")
    business_type = st.text_input("Business type", "restaurants")
    service = st.text_input("Service you sell", "bookkeeping and basic financial reporting")
    ideal_customer = st.text_area("Ideal customer", "Small owner-managed businesses that may benefit from recurring bookkeeping, Excel cleanup, reconciliation, or simple monthly reports.", height=110)
    count = st.slider("Businesses to analyze", 5, 30, 10)
    model = st.text_input("Local Ollama model", "qwen3:4b")
    st.divider(); st.subheader("Lead quality filters")
    enrich = st.checkbox("Deep public-web enrichment", True)
    require_contact = st.checkbox("Remove leads with no public contact/profile", True)
    require_website = st.checkbox("Remove leads with no public website", False)
    crawl_pages = st.slider("Pages to scan per website", 3, 30, 15, help="Scans only public pages on the same domain. More pages = slower search.")
    run = st.button("Find leads", type="primary", use_container_width=True)

if run:
    query=f"{business_type} in {location}"
    with st.status("Finding and qualifying businesses...",expanded=True) as status:
        try:
            st.write(f"1/4 — Finding candidate businesses: `{query}`")
            places=search_places(location,business_type,count*3 if enrich else count)
            st.write(f"Found {len(places)} initial candidates.")
            if not places: status.update(label="No businesses found",state="error"); st.stop()
            st.write("2/4 — Searching public web results and business websites...")
            st.write(f"3/4 — Crawling up to {crawl_pages} public pages per candidate and looking for contact/decision-maker evidence...")
            leads=qualify_leads(places,service,ideal_customer,model,enrich=enrich,location=location,require_contact=require_contact,require_website=require_website,crawl_pages=crawl_pages)
            st.write(f"4/4 — AI qualification complete. {len(leads)} usable leads remain after filters.")
            local=sum(1 for x in leads if x.get("ai_mode")=="Local AI")
            if len(leads)>count: leads=leads[:count]
            status.update(label=f"Done — {len(leads)} leads",state="complete")
        except Exception as exc:
            status.update(label="Search failed",state="error"); st.exception(exc); st.stop()

    st.subheader(f"Qualified leads ({len(leads)})")
    for i,lead in enumerate(leads,1):
        score=lead["score"]; icon="🔥" if score>=80 else "🟡" if score>=60 else "⚪"
        with st.expander(f"{i}. {lead['business_name']} — {score}/100 {icon}"):
            c1,c2=st.columns([1,1])
            with c1:
                st.write(f"**Address:** {lead.get('address') or 'Unknown'}")
                st.write(f"**Type:** {lead.get('type') or 'Unknown'}")
                st.write(f"**Website:** {lead.get('website') or 'Not found'}")
                st.write(f"**Emails:** {', '.join(lead.get('public_emails',[])) or 'Not found'}")
                st.write(f"**Phones:** {', '.join(lead.get('public_phones',[])) or 'Not found'}")
                st.write(f"**Website pages scanned:** {lead.get('website_pages_scanned',0)}")
                if lead.get("contact_page"): st.markdown(f"[Contact page]({lead['contact_page']})")
            with c2:
                st.write(f"**Fit:** {lead['fit']} · **Scoring:** {lead.get('ai_mode','Unknown')}")
                st.write("**Public profiles:**")
                labels=[("LinkedIn","linkedin"),("Instagram","instagram"),("Facebook","facebook"),("TikTok","tiktok"),("YouTube","youtube"),("X","x"),("WhatsApp","whatsapp")]
                shown=False
                for label,key in labels:
                    if lead.get(key): shown=True; st.markdown(f"- [{label}]({lead[key]})")
                if not shown: st.caption("No public social/profile link found")
                if lead.get("decision_maker_evidence"):
                    st.write("**Decision-maker evidence (verify):**")
                    for item in lead["decision_maker_evidence"][:3]: st.caption(item)
                st.write("**Why it may fit:**")
                for reason in lead.get("reasons",[]): st.write(f"- {reason}")
            st.write("**Suggested service:**",lead.get("suggested_service",service))
            st.write("**Draft outreach:**"); st.code(lead.get("outreach",""),language=None)
            if lead.get("google_maps"): st.markdown(f"[Open in Google Maps]({lead['google_maps']})")
            if lead.get("search_sources"):
                with st.expander("Public sources used"):
                    for src in lead["search_sources"]: st.write(src)
            if lead.get("unknowns"): st.caption("Verify before contacting: "+"; ".join(lead["unknowns"]))

    export=pd.DataFrame(leads)
    for col in ["reasons","unknowns","public_emails","public_phones","decision_maker_evidence","website_pages","search_sources"]:
        if col in export: export[col]=export[col].apply(lambda x:" | ".join(map(str,x)) if isinstance(x,list) else x)
    st.download_button("Download enriched leads as CSV",export.to_csv(index=False).encode("utf-8"),file_name="ai_enriched_leads.csv",mime="text/csv")
else:
    st.info("Set your search criteria and click **Find leads**.")
    st.markdown("**Recommended test:** Kuala Lumpur → restaurants → bookkeeping → 10 leads → Deep enrichment ON → Remove no-contact ON.")
    st.warning("Only public information is collected. The app does not log into LinkedIn/social networks, bypass privacy controls, or try to obtain private contact data. Verify contacts and comply with applicable outreach/privacy rules before messaging.")
