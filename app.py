import pandas as pd
import streamlit as st

from lead_finder import qualify_leads, search_places

st.set_page_config(page_title="AI Lead Finder — Free", page_icon="🎯", layout="wide")

st.title("🎯 AI Lead Finder — Free MVP")
st.caption("Find public business leads with OpenStreetMap and qualify them with a local AI model. No paid API keys required.")

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
    count = st.slider("Businesses to analyze", 5, 20, 10)
    model = st.text_input("Local Ollama model", "qwen3:4b")
    run = st.button("Find leads", type="primary", use_container_width=True)

if run:
    query = f"{business_type} in {location}"
    with st.status("Finding and qualifying businesses...", expanded=True) as status:
        st.write(f"Searching public OpenStreetMap data for: `{query}`")
        try:
            places = search_places(location, business_type, count)
            st.write(f"Found {len(places)} businesses.")
            if not places:
                status.update(label="No businesses found", state="error")
                st.stop()

            st.write(f"Trying local AI model: `{model}`")
            leads = qualify_leads(places, service, ideal_customer, model)
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
                st.write(f"**Phone:** {lead['phone'] or 'Unknown'}")
            with c2:
                st.write(f"**Fit:** {lead['fit']}")
                st.write("**Why it may fit:**")
                for reason in lead["reasons"]:
                    st.write(f"- {reason}")
                st.write(f"**Suggested service:** {lead['suggested_service']}")

            st.write("**Draft outreach:**")
            st.code(lead["outreach"], language=None)
            if lead["google_maps"]:
                st.markdown(f"[Open in Google Maps]({lead['google_maps']})")
            if lead["unknowns"]:
                st.caption("Verify before contacting: " + "; ".join(lead["unknowns"]))

    export = pd.DataFrame(leads)
    export["reasons"] = export["reasons"].apply(lambda x: " | ".join(x))
    export["unknowns"] = export["unknowns"].apply(lambda x: " | ".join(x))
    st.download_button(
        "Download leads as CSV",
        export.to_csv(index=False).encode("utf-8"),
        file_name="ai_leads.csv",
        mime="text/csv",
    )
else:
    st.info("Set your search criteria on the left and click **Find leads**.")
    st.markdown("**First test:** `Kuala Lumpur` → `restaurants` → `bookkeeping` → 10 leads.")
    st.markdown("**Free stack:** OpenStreetMap/Overpass for public place data + Ollama for local AI. Ollama can run models locally on Windows without a paid API key.")
