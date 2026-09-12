"""Minimal UI (PRD §7: "CLI first -> Streamlit/FastAPI once pipeline is proven").

Run: .venv/Scripts/streamlit run src/app.py
"""
import streamlit as st

from generate import answer_query

st.set_page_config(page_title="IP-SAKTI Sahayak", page_icon="⚖️")

st.title("IP-SAKTI Sahayak")
st.caption(
    "Ayurveda IP & regulatory guidance — answers only from the source corpus, "
    "with every claim checked against its cited passage before being shown."
)

with st.expander("Known limitations", expanded=False):
    st.markdown(
        "- Uses a local LLM (Qwen 2.5 7B via Ollama), not the Claude API — see `docs/decisions.md`.\n"
        "- Terse statutory clauses (e.g. Patents Act §3(p)) don't always rank highly for "
        "natural-language questions; the system may answer from a secondary source instead.\n"
        "- English-only corpus so far.\n"
        "- Single-user, local-only — not built for concurrent production use."
    )

query = st.text_input("Ask a question about Ayurveda IP/regulatory law:")

if st.button("Ask", type="primary") and query.strip():
    with st.spinner("Retrieving, verifying, and generating a grounded answer..."):
        result = answer_query(query)

    if result["refused"]:
        st.warning(result["answer"])
    else:
        st.markdown(result["answer"])
        with st.expander("Sources cited"):
            for c in result["citations"]:
                st.markdown(f"- {c}")
