from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict

app = FastAPI()

class AnalyzeRequest(BaseModel):
    conversationId: str
    message: str
    data: Dict[str, Any]  # {"headers": [...], "data": [[...], ...]}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    headers = req.data.get("headers", [])
    rows = req.data.get("data", [])
    return {
        "conversationId": req.conversationId,
        "result": {
            "answer": f"Received {len(rows)} rows and {len(headers)} columns. Question: {req.message}",
            "risks": [],
            "score": 50,
            "nextQuestions": [
                "What are the top 5 revenue drivers?",
                "Is profit margin changing over time?"
            ]
        }
    }
