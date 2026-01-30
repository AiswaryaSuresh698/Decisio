import io
import uuid
import pandas as pd
import streamlit as st
import requests

st.set_page_config(page_title="Decisio", layout="wide")
st.title("Decisio — Excel Upload → Colab Brain")

# ✅ Put your Colab public URL here (example: https://xxxxxx-5002.../ )
COLAB_API_BASE = st.secrets.get("COLAB_API_BASE", "https://5002-m-s-1j12d0m5j9ovh-c.us-west4-0.prod.colab.dev").rstrip("/")

# Session-level conversationId (matches your backend requirement)
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

max_rows = st.number_input("Rows to send to backend (limit for speed)", min_value=10, max_value=2000, value=200, step=10)
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

def df_to_backend_payload(df: pd.DataFrame, limit_rows: int):
    df2 = df.copy()
    # Make values JSON-safe (avoid NaN/NaT issues)
    df2 = df2.where(pd.notnull(df2), None)

    headers = [str(c) for c in df2.columns.tolist()]
    rows = df2.head(limit_rows).values.tolist()
    return {"headers": headers, "data": rows}

def call_colab_analyze(conversation_id: str, message: str, excel_payload: dict):
    url = f"{COLAB_API_BASE}/analyze"
    payload = {
        "conversationId": conversation_id,
        "message": message,
        "data": excel_payload
    }
    r = requests.post(url, json=payload, timeout=120)
    r.raise_for_status()
    return r.json()

def call_colab_health():
    url = f"{COLAB_API_BASE}/health"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()

# ------------------------
# Run
# ------------------------
if st.button("Test backend /health"):
    try:
        health = call_colab_health()
        st.success("Backend reachable")
        st.json(health)
    except Exception as e:
        st.error("Health check failed")
        st.code(str(e))

if uploaded:
    try:
        df, used_sheet = read_excel(uploaded, sheet_name)
        st.subheader(f"Preview (sheet: {used_sheet})")
        st.dataframe(df.head(25), use_container_width=True)
    except Exception as e:
        st.error("Failed to read Excel")
        st.code(str(e))
        st.stop()

    if st.button("Run Decisio (Colab Backend)", type="primary"):
        try:
            excel_payload = df_to_backend_payload(df, int(max_rows))

            resp = call_colab_analyze(
                conversation_id=st.session_state.conversation_id,
                message=prompt,
                excel_payload=excel_payload
            )

            st.success("Analysis completed")
            st.subheader("Raw response")
            st.json(resp)

            # Your backend returns: {"conversationId":..., "result": {...}}
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
else:
    st.info("Upload an Excel file to begin.")

