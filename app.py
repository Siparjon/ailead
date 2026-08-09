import pandas as pd
import streamlit as st

from lead_finder import qualify_leads, search_places

st.set_page_config(page_title="AI Lead Finder — Free", page_icon="🎯", layout="wide")

st.title("🎯 AI Lead Finder — Free")
st.caption("Find businesses from OpenStreetMap + public web search, enrich public contacts/socials, and qualify leads with local AI. No paid API keys required.")

with st.sidebar:
    st.header("Search")
    location = st.text_input("Location", "Kuala Lumpur, Malaysia")
    business_type = st.text_input("Business type", "restaurants")
    service = st.text_input("Service you sell", "bookkeeping and basic financial reporting")
    ideal_customer = st.text_area(
        "Ideal customer",
        "Small owner-managed businesses that may benefit from recurring bookkeeping, Excel cleanup, reconciliation, or simple monthly reports.",
        height=110,
    )
    count = st.slider("Businesses to analyze", 5, 30, 10)
    model = st.text_input("Local Ollama model", "qwen3:4b")
    enrich = st.checkbox("Enrich with public web/contact/social data", True)
    run = st.button("Find leads", type="primary", use_container_width=True)

if run:
    query = f"{business_type} in {location}"
    with st.status("Finding and qualifying businesses...", expanded=True) as status:
        st.write(f"1/3 — Searching public OpenStreetMap data for: `{query}`")
        try:
            places = search_places(location, business_type, count)
            st.write(f"Found {len(places)} businesses.")
            if not places:
                status.update(label="No businesses found", state="error")
                st.stop()

            st.write("2/3 — Enriching public websites, emails, phones and social/profile links...")
            st.write("3/3 — Scoring leads with the local AI model...")
            leads = qualify_leads(places, service, ideal_customer, model, enrich=enrich)
            local_ai_count = sum(1 for x in leads if x.get("ai_mode") == "Local AI")
            fallback_count = len(leads) - local_ai_count
            if fallback_count:
                st.write(f"Local AI unavailable for {fallback_count} lead(s); used free rule-based fallback.")
            status.update(label=f"Done — {len(leads)} leads qualified", state="complete")
        except Exception as exc:
            status.update(label="Search failed", state="error")
            st.exception(exc)
            st.stop()

    st.subheader("Qualified leads")

    for i, lead in enumerate(leads, start=1):
        score = lead["score"]
        label = "🔥" if score >= 80 else "🟡" if score >= 60 else "⚪"
        with st.expander(f"{i}. {lead['business_name']} — {score}/100 {label}"):
            st.caption(f"Scoring: {lead.get('ai_mode', 'Unknown')}")
            c1, c2 = st.columns([1, 1])
            with c1:
                st.write(f"**Address:** {lead['address'] or 'Unknown'}")
                st.write(f"**Type:** {lead['type'] or 'Unknown'}")
                st.write(f"**Website:** {lead['website'] or 'Unknown'}")
                st.write(f"**Business phone:** {lead['phone'] or 'Unknown'}")
                emails = lead.get("public_emails", [])
                phones = lead.get("public_phones", [])
                st.write(f"**Public emails:** {', '.join(emails) if emails else 'Not found'}")
                st.write(f"**Public phones:** {', '.join(phones) if phones else 'Not found'}")
            with c2:
                st.write(f"**Fit:** {lead['fit']}")
                st.write("**Public profiles:**")
                profiles = [
                    ("LinkedIn", lead.get("linkedin")), ("Instagram", lead.get("instagram")),
                    ("Facebook", lead.get("facebook")), ("TikTok", lead.get("tiktok")),
                    ("YouTube", lead.get("youtube")), ("X", lead.get("x")), ("WhatsApp", lead.get("whatsapp")),
                ]
                found_profiles = False
                for label_name, url in profiles:
                    if url:
                        found_profiles = True
                        st.markdown(f"- [{label_name}]({url})")
                if not found_profiles:
                    st.caption("No public social/profile link found")
                st.write("**Why it may fit:**")
                for reason in lead["reasons"]:
                    st.write(f"- {reason}")
                st.write(f"**Suggested service:** {lead['suggested_service']}")

            st.write("**Draft outreach:**")
            st.code(lead["outreach"], language=None)
            if lead.get("contact_page"):
                st.markdown(f"[Open contact page]({lead['contact_page']})")
            if lead.get("google_maps"):
                st.markdown(f"[Open in Google Maps]({lead['google_maps']})")
            if lead.get("search_sources"):
                with st.expander("Public web sources used"):
                    for source in lead["search_sources"]:
                        st.write(source)
            if lead["unknowns"]:
                st.caption("Verify before contacting: " + "; ".join(lead["unknowns"]))

    export = pd.DataFrame(leads)
    for col in ["reasons", "unknowns", "public_emails", "public_phones"]:
        if col in export:
            export[col] = export[col].apply(lambda x: " | ".join(x) if isinstance(x, list) else x)
    if "socials" in export:
        export["socials"] = export["socials"].apply(lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, dict) else x)
    st.download_button(
        "Download enriched leads as CSV",
        export.to_csv(index=False).encode("utf-8"),
        file_name="ai_enriched_leads.csv",
        mime="text/csv",
    )
else:
    st.info("Set your search criteria on the left and click **Find leads**.")
    st.markdown("**Example:** `Kuala Lumpur` → `restaurants` → `bookkeeping` → 10 leads")
    st.markdown("**Free stack:** OpenStreetMap/Overpass + public web search + public websites + Ollama local AI. The app does not log into or bypass LinkedIn, Instagram, Facebook, or other sites.")
