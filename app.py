import uuid
import pandas as pd
import streamlit as st
import requests

from backend_client import (
    df_to_backend_payload,
    call_colab_analyze,
    call_colab_health,
)
from templates import (
    infer_mapping,
    available_templates,
    render_overview,
    render_product,
    render_geo,
    render_customer,
)

st.set_page_config(page_title="Decisio", layout="wide")
st.title("Decisio — Excel Upload → Templates + Chat Brain")

COLAB_API_BASE = st.secrets.get(
    "COLAB_API_BASE",
    "https://5002-m-s-1j12d0m5j9ovh-c.us-west4-0.prod.colab.dev"
).rstrip("/")

if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = str(uuid.uuid4())

# ------------------------
# UI
# ------------------------
uploaded = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])

prompt = st.text_input(
    "What do you want Decisio to do?",
    value="Summarize the provided data and highlight key risks."
)

max_rows = st.number_input(
    "Rows to send to backend (limit for speed)",
    min_value=10, max_value=2000, value=200, step=10
)

sheet_name = st.text_input("Sheet name (leave blank for first sheet)", value="")

col1, col2 = st.columns(2)
with col1:
    st.write("Conversation ID:", st.session_state.conversation_id)
with col2:
    if st.button("New Conversation ID"):
        st.session_state.conversation_id = str(uuid.uuid4())
        st.rerun()

# ------------------------
# Helpers
# ------------------------
def read_excel(uploaded_file, sheet: str):
    uploaded_file.seek(0)
    xls = pd.ExcelFile(uploaded_file)
    use_sheet = sheet.strip() if sheet and sheet.strip() in xls.sheet_names else xls.sheet_names[0]
    df = pd.read_excel(xls, sheet_name=use_sheet)
    return df, use_sheet

# ------------------------
# Run
# ------------------------
if st.button("Test backend /health"):
    try:
        health = call_colab_health(COLAB_API_BASE)
        st.success("Backend reachable")
        st.json(health)
    except Exception as e:
        st.error("Health check failed")
        st.code(str(e))

if not uploaded:
    st.info("Upload an Excel file to begin.")
    st.stop()

# Read + preview
try:
    df, used_sheet = read_excel(uploaded, sheet_name)
    st.subheader(f"Preview (sheet: {used_sheet})")
    st.dataframe(df.head(25), use_container_width=True)
except Exception as e:
    st.error("Failed to read Excel")
    st.code(str(e))
    st.stop()

# ------------------------
# Templates (local)
# ------------------------
mapping = infer_mapping(df)
templates = available_templates(mapping)

st.divider()
st.subheader("Templates")

if not templates:
    st.warning("No templates available (need at least a Revenue/Sales numeric column).")
else:
    # Sidebar: Chat with your data (calls Colab /analyze)
    with st.sidebar.expander("💬 Chat with your data", expanded=True):
        chat_q = st.text_input("Ask a question", placeholder="e.g., Which category drives most profit?")
        if st.button("Ask (Colab Brain)", key="ask_brain"):
            try:
                excel_payload = df_to_backend_payload(df, int(max_rows))
                resp = call_colab_analyze(
                    colab_api_base=COLAB_API_BASE,
                    conversation_id=st.session_state.conversation_id,
                    message=chat_q,
                    excel_payload=excel_payload
                )
                result = (resp or {}).get("result", {})
                st.write(result.get("answer", ""))

                nq = result.get("nextQuestions", [])
                if isinstance(nq, list) and nq:
                    st.caption("Next questions")
                    for q in nq[:5]:
                        st.write(f"• {q}")
            except Exception as e:
                st.error("Chat request failed")
                st.code(str(e))

    # Main: template selector
    template_labels = [label for _, label in templates]
    selected_label = st.radio("Select a template", template_labels, index=0, horizontal=True)
    selected_id = next(tid for tid, label in templates if label == selected_label)

    if selected_id == "overview":
        render_overview(st, df, mapping)
    elif selected_id == "product":
        render_product(st, df, mapping)
    elif selected_id == "geo":
        render_geo(st, df, mapping)
    elif selected_id == "customer":
        render_customer(st, df, mapping)

    with st.expander("Detected Mapping (debug)"):
        st.json(mapping)

# ------------------------
# Your existing “Run Decisio” backend analysis
# ------------------------
st.divider()
if st.button("Run Decisio (Colab Backend)", type="primary"):
    try:
        excel_payload = df_to_backend_payload(df, int(max_rows))
        resp = call_colab_analyze(
            colab_api_base=COLAB_API_BASE,
            conversation_id=st.session_state.conversation_id,
            message=prompt,
            excel_payload=excel_payload
        )

        st.success("Analysis completed")
        st.subheader("Raw response")
        st.json(resp)

        result = (resp or {}).get("result", {})

        st.subheader("Answer")
        st.write(result.get("answer", ""))

        st.subheader("Risks")
        risks = result.get("risks", [])
        if isinstance(risks, list) and risks:
            for r in risks:
                st.write(f"• {r}")
        else:
            st.write("No risks returned.")

        st.subheader("Score")
        st.write(result.get("score", None))

        st.subheader("Next Questions")
        nq = result.get("nextQuestions", [])
        if isinstance(nq, list) and nq:
            for q in nq:
                st.write(f"• {q}")
        else:
            st.write("None returned.")

    except requests.exceptions.RequestException as e:
        st.error("Backend request failed")
        st.code(str(e))
    except Exception as e:
        st.error("Unexpected error")
        st.code(str(e))

