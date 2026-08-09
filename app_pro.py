import pandas as pd
import streamlit as st

from lead_finder import search_places
from lead_finder_pro import qualify_pro, load_crm, upsert_crm

st.set_page_config(page_title="AI Lead Finder Pro", page_icon="🎯", layout="wide")
st.title("🎯 AI Lead Finder Pro")
st.caption("Free public-web research + local AI. Decision makers, pain points, multi-score qualification, personalized outreach, and a simple local CRM.")

with st.sidebar:
    st.header("Search")
    location = st.text_input("Location", "Kuala Lumpur, Malaysia")
    business_type = st.text_input("Business type", "digital agencies")
    service = st.text_input("Service you sell", "basic bookkeeping and monthly financial reporting")
    ideal_customer = st.text_area("Ideal customer", "Small owner-managed businesses that can pay $150-200/month for recurring bookkeeping support.", height=100)
    count = st.slider("Leads to return", 5, 25, 10)
    model = st.text_input("Local Ollama model", "qwen3:4b")
    crawl_pages = st.slider("Website pages per candidate", 1, 10, 5)
    run = st.button("Find qualified leads", type="primary", use_container_width=True)

if run:
    with st.status("Researching leads...", expanded=True) as status:
        try:
            st.write("1/3 — Finding candidate businesses...")
            candidates = search_places(location, business_type, count * 2)
            st.write(f"Found {len(candidates)} candidates.")
            if not candidates:
                status.update(label="No candidates found", state="error")
                st.stop()
            st.write("2/3 — Finding public contacts and decision-maker evidence...")
            leads=[]
            for i, raw in enumerate(candidates, 1):
                st.write(f"Researching {i}/{len(candidates)}: {raw['business_name']}")
                lead = qualify_pro(raw, location, service, ideal_customer, model, crawl_pages)
                has_contact = bool(lead.get("public_emails") or lead.get("public_phones") or lead.get("linkedin") or lead.get("instagram") or lead.get("facebook") or lead.get("whatsapp"))
                if not has_contact:
                    continue
                leads.append(lead)
            leads = sorted(leads, key=lambda x: x.get("score", 0), reverse=True)[:count]
            st.write(f"3/3 — Qualified {len(leads)} leads.")
            status.update(label=f"Done — {len(leads)} qualified leads", state="complete")
        except Exception as exc:
            status.update(label="Search failed", state="error")
            st.exception(exc)
            st.stop()

    st.subheader(f"Qualified leads ({len(leads)})")
    for i, lead in enumerate(leads, 1):
        score = lead.get("score", 0); icon = "🔥" if score >= 80 else "🟡" if score >= 60 else "⚪"
        with st.expander(f"{i}. {lead['business_name']} — {score}/100 {icon}"):
            a,b,c,d = st.columns(4)
            a.metric("Overall", lead.get("score",0))
            b.metric("Business fit", lead.get("business_fit_score",0))
            c.metric("Need", lead.get("potential_need_score",0))
            d.metric("Contactability", lead.get("contactability_score",0))
            st.write(f"**Decision-maker confidence:** {lead.get('decision_maker_score',0)}/100")
            if lead.get("decision_maker"):
                st.success(f"Decision maker: {lead['decision_maker']}")
            elif lead.get("decision_makers"):
                st.info("Possible decision-maker evidence: " + "; ".join(x.get("name", "") for x in lead["decision_makers"][:3]))
            else:
                st.caption("No verified decision-maker name found in public data.")

            left,right=st.columns(2)
            with left:
                st.write(f"**Website:** {lead.get('website') or 'Not found'}")
                st.write(f"**Email:** {', '.join(lead.get('public_emails',[])) or 'Not found'}")
                st.write(f"**Phone:** {', '.join(lead.get('public_phones',[])) or 'Not found'}")
                st.write(f"**Recommended channel:** {lead.get('recommended_channel','Email')}")
                if lead.get("linkedin"): st.markdown(f"[LinkedIn]({lead['linkedin']})")
                if lead.get("instagram"): st.markdown(f"[Instagram]({lead['instagram']})")
                if lead.get("whatsapp"): st.markdown(f"[WhatsApp]({lead['whatsapp']})")
            with right:
                st.write("**Potential pain points — verify before outreach:**")
                for x in lead.get("pain_points",[]): st.write(f"- {x}")
                st.write("**Why it may fit:**")
                for x in lead.get("reasons",[]): st.write(f"- {x}")
                if lead.get("unknowns"): st.caption("Unknown: " + "; ".join(lead["unknowns"]))

            st.write("### Personalized outreach")
            tabs=st.tabs(["Email","LinkedIn","DM"])
            with tabs[0]: st.code(lead.get("outreach_email", ""))
            with tabs[1]: st.code(lead.get("outreach_linkedin", ""))
            with tabs[2]: st.code(lead.get("outreach_dm", ""))

            st.write("### CRM")
            cc1,cc2,cc3=st.columns([1,1,2])
            status=cc1.selectbox("Status",["New","Contacted","Replied","Interested","Call booked","Client","Rejected"],key=f"status_{i}")
            follow=cc2.text_input("Next follow-up",key=f"follow_{i}",placeholder="2026-08-14")
            notes=cc3.text_input("Notes",key=f"notes_{i}")
            if st.button("Save to CRM",key=f"save_{i}"):
                upsert_crm(lead,status,notes,follow); st.success("Saved")

    df=pd.DataFrame(leads)
    for col in ["reasons","pain_points","unknowns","public_emails","public_phones","decision_makers","search_sources"]:
        if col in df: df[col]=df[col].apply(lambda x:" | ".join(map(str,x)) if isinstance(x,list) else x)
    st.download_button("Download qualified leads CSV",df.to_csv(index=False).encode("utf-8"),"qualified_leads.csv","text/csv")

st.divider(); st.subheader("📌 CRM / Follow-ups")
crm=load_crm()
if crm:
    st.dataframe(pd.DataFrame(crm),use_container_width=True,hide_index=True)
else:
    st.info("No CRM records yet. Save a lead above after contacting or qualifying it.")
