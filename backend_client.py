import pandas as pd
import requests

def df_to_backend_payload(df: pd.DataFrame, limit_rows: int) -> dict:
    """
    Converts a dataframe to the payload format expected by your Colab backend:
      {
        "headers": [...],
        "data": [[...], ...]
      }
    """
    df2 = df.copy()

    # Convert datetime columns to ISO strings
    for col in df2.columns:
        if pd.api.types.is_datetime64_any_dtype(df2[col]):
            df2[col] = df2[col].dt.strftime("%Y-%m-%d %H:%M:%S")

    # Replace NaN / NaT with None (JSON-safe)
    df2 = df2.where(pd.notnull(df2), None)

    headers = [str(c) for c in df2.columns.tolist()]
    rows = df2.head(int(limit_rows)).values.tolist()

    return {"headers": headers, "data": rows}


def call_colab_analyze(colab_api_base: str, conversation_id: str, message: str, excel_payload: dict) -> dict:
    url = f"{colab_api_base.rstrip('/')}/analyze"
    payload = {
        "conversationId": conversation_id,
        "message": message,
        "data": excel_payload
    }
    r = requests.post(url, json=payload, timeout=120)
    r.raise_for_status()
    return r.json()


def call_colab_health(colab_api_base: str) -> dict:
    url = f"{colab_api_base.rstrip('/')}/health"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()
