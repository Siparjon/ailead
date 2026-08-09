import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

from lead_finder import qualify_leads, search_places

load_dotenv()

st.set_page_config(page_title="AI Lead Finder", page_icon="🎯", layout="wide")

st.title("🎯 AI Lead Finder")
st.caption("Find public business leads, qualify them with AI, and prepare outreach.")

with st.sidebar:
    st.header("Search")
    location = st.text_input("Location", "Kuala Lumpur, Malaysia")
    business_type = st.text_input("Business type", "small businesses")
    service = st.text_input("Service you sell", "bookkeeping and basic financial reporting")
    ideal_customer = st.text_area(
        "Ideal customer",
        "Small owner-managed businesses that may benefit from recurring bookkeeping, Excel cleanup, reconciliation, or simple monthly reports.",
        height=110,
    )
    count = st.slider("Businesses to analyze", 5, 20, 10)
    run = st.button("Find leads", type="primary", use_container_width=True)

if run:
    openai_key = os.getenv("OPENAI_API_KEY")
    google_key = os.getenv("GOOGLE_MAPS_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-5-mini")

    if not openai_key or not google_key:
        st.error("Add OPENAI_API_KEY and GOOGLE_MAPS_API_KEY to your .env file first.")
        st.stop()

    query = f"{business_type} in {location}"
    with st.status("Finding and qualifying businesses...", expanded=True) as status:
        st.write(f"Searching: `{query}`")
        try:
            places = search_places(query, google_key, count)
            st.write(f"Found {len(places)} businesses.")
            if not places:
                status.update(label="No businesses found", state="error")
                st.stop()

            st.write("AI is scoring each business...")
            client = OpenAI(api_key=openai_key)
            leads = qualify_leads(places, service, ideal_customer, client, model)
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
            c1, c2 = st.columns([1, 1])
            with c1:
                st.write(f"**Address:** {lead['address'] or 'Unknown'}")
                st.write(f"**Type:** {lead['type'] or 'Unknown'}")
                st.write(f"**Rating:** {lead['rating'] or 'Unknown'} ({lead['review_count'] or 0} reviews)")
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
    st.markdown(
        "**First test:** `Kuala Lumpur` → `small restaurants` → `bookkeeping` → 10 leads."
    )
