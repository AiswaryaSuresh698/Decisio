
import os
import json
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from openai import OpenAI
import boto3


app = FastAPI()

# ---------- OpenAI client ----------
# Reads OPENAI_API_KEY from environment, per official SDK usage. :contentReference[oaicite:1]{index=1}
openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# ---------- AWS / DynamoDB (optional) ----------
AWS_REGION = os.environ.get("AWS_REGION", "")
DDB_TABLE = os.environ.get("DDB_TABLE", "")

ddb = None
table = None
if AWS_REGION and DDB_TABLE:
    ddb = boto3.resource("dynamodb", region_name=AWS_REGION)
    table = ddb.Table(DDB_TABLE)


class AnalyzeRequest(BaseModel):
    conversationId: str
    message: str
    data: Dict[str, Any]  # {"headers": [...], "data": [[...], ...]}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "openai_key_set": bool(os.environ.get("OPENAI_API_KEY")),
        "ddb_enabled": bool(table),
        "ddb_table": DDB_TABLE if table else None,
    }


def _safe_preview(data: Dict[str, Any], max_rows: int = 50) -> Dict[str, Any]:
    headers = data.get("headers", [])
    rows = data.get("data", []) or []
    return {"headers": headers, "rows": rows[:max_rows]}


def _save_to_ddb(conversation_id: str, user_msg: str, assistant_msg: str) -> None:
    if not table:
        return
    table.put_item(
        Item={
            "conversationId": conversation_id,
            "ts": int(__import__("time").time()),
            "user": user_msg,
            "assistant": assistant_msg,
        }
    )


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not set on server")

    preview = _safe_preview(req.data, max_rows=60)
    headers = preview["headers"]
    rows = preview["rows"]

    # Build a compact context for the model (avoid sending huge payloads)
    # You can improve this later (profiling, aggregation, etc.)
    context = {
        "columns": headers,
        "sample_rows": rows[:20],
        "row_count_sent": len(rows),
    }

    system_instructions = (
        "You are Decisio, a business analytics assistant. "
        "Answer using ONLY the provided dataset context. "
        "Return concise actionable insights."
    )

    user_input = f"""
User question:
{req.message}

Dataset context (JSON):
{json.dumps(context, ensure_ascii=False)}
"""

    try:
        # Responses API is the primary recommended API for new projects. :contentReference[oaicite:2]{index=2}
        resp = openai_client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": user_input},
            ],
        )

        answer_text = resp.output_text or ""

        # Minimal “structured-ish” output for your existing UI schema
        result = {
            "answer": answer_text,
            "risks": [],
            "score": 50,
            "nextQuestions": [
                "What are the top 5 drivers of revenue?",
                "Which segments have the lowest margins?",
                "What trend do you see over time (if date exists)?",
            ],
        }

        _save_to_ddb(req.conversationId, req.message, answer_text)

        return {"conversationId": req.conversationId, "result": result}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
