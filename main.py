from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import re
from datetime import datetime
from dateutil import parser
import requests

app = FastAPI()

# ---- Request Model ----
class ExtractRequest(BaseModel):
    text: str

# ---- Response Model ----
class ExtractResponse(BaseModel):
    vendor: str
    amount: float
    currency: str = Field(..., min_length=3, max_length=3)
    date: str  # YYYY-MM-DD


# ---- Helper: Call Local LLM (Ollama) ----
def call_llm(text: str):
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3",
                "prompt": f"""
Extract the following fields from the invoice text:

- vendor (string)
- amount (number)
- currency (3-letter uppercase)
- date (YYYY-MM-DD)

Return ONLY JSON like:
{{"vendor": "...", "amount": 123.45, "currency": "USD", "date": "2026-05-10"}}

Invoice:
{text}
""",
                "stream": False
            },
            timeout=10
        )

        return response.json()["response"]
    except:
        return None


# ---- Fallback Extraction (Regex) ----
def fallback_extract(text: str):
    # Vendor (simple heuristic: first line or company-like name)
    vendor_match = re.search(r"([A-Za-z0-9\-\s]+(?:Ltd|Inc|Industries|Corp))", text, re.I)
    vendor = vendor_match.group(1) if vendor_match else "Unknown Vendor"

    # Amount
    amount_match = re.search(r"(\d+(\.\d{1,2})?)", text)
    amount = float(amount_match.group(1)) if amount_match else 0.0

    # Currency
    currency_match = re.search(r"\b(USD|EUR|GBP)\b", text)
    currency = currency_match.group(1) if currency_match else "USD"

    # Date
    date_match = re.search(r"(2026-\d{2}-\d{2})", text)
    if date_match:
        date = date_match.group(1)
    else:
        try:
            parsed = parser.parse(text, fuzzy=True)
            date = parsed.strftime("%Y-%m-%d")
        except:
            date = "2026-01-01"

    return {
        "vendor": vendor.strip(),
        "amount": amount,
        "currency": currency.upper(),
        "date": date
    }


# ---- Main Endpoint ----
@app.post("/extract", response_model=ExtractResponse)
def extract_invoice(data: ExtractRequest):
    text = data.text.strip()

    if not text:
        raise HTTPException(status_code=422, detail="Empty input")

    # Try LLM first
    llm_output = call_llm(text)

    if llm_output:
        try:
            import json
            parsed = json.loads(llm_output)

            return ExtractResponse(
                vendor=parsed.get("vendor", ""),
                amount=float(parsed.get("amount", 0)),
                currency=parsed.get("currency", "USD").upper(),
                date=parsed.get("date", "")
            )
        except:
            pass  # fallback if parsing fails

    # Fallback
    extracted = fallback_extract(text)

    return ExtractResponse(**extracted)