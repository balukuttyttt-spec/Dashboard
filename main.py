from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from datetime import datetime, date
import uvicorn
import os
import requests
import json

app = FastAPI()

# Fallback: Check if 'templates' folder exists, otherwise use current folder
if os.path.exists("templates"):
    templates = Jinja2Templates(directory="templates")
else:
    templates = Jinja2Templates(directory=".")

# In-memory storage
signals = []
stats = {
    "total_trades": 0,
    "today_trades": 0,
    "wins": 0,
    "losses": 0,
    "win_rate": 0.0
}

# GOOGLE APPS SCRIPT URL (For Persistence)
GAS_URL = "https://script.google.com/macros/s/AKfycbzmoFvNtRZgc2t6zRaLmtlPibmEIJgyaXsWC0hgKuLUNhFwKeCiT6LquLyzcZ7hAyOv/exec"

class Signal(BaseModel):
    action: str
    ticker: str
    price: float
    sl: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    tp3: float = 0.0
    # Optional fields
    result: str = None
    comment: str = None
    # Fields for Telegram
    chat_id: str = None
    text: str = None

@app.on_event("startup")
async def startup_event():
    """Fetch history from Google Sheet on startup"""
    global signals, stats
    print("🔄 Fetching history from Google Sheet...")
    try:
        response = requests.get(GAS_URL)
        if response.status_code == 200:
            history = response.json()
            if isinstance(history, list):
                signals = history
                print(f"✅ Loaded {len(signals)} trades from history.")
                
                # Re-calculate Stats
                stats["total_trades"] = len(signals)
                stats["wins"] = sum(1 for s in signals if s.get("action", "").lower() == "win")
                stats["losses"] = sum(1 for s in signals if s.get("action", "").lower() == "loss")
                
                total_closed = stats["wins"] + stats["losses"]
                stats["win_rate"] = (stats["wins"] / total_closed * 100) if total_closed > 0 else 0.0
                
                # Count today's trades
                today_str = date.today().strftime("%Y-%m-%d")
                stats["today_trades"] = sum(1 for s in signals if s.get("date") == today_str)
            else:
                print("⚠️ History format invalid (not a list).")
        else:
            print(f"❌ Failed to fetch history: {response.status_code}")
    except Exception as e:
        print(f"❌ Error fetching history: {e}")

@app.post("/webhook")
async def webhook(request: Request):
    # 1. Parse JSON manually to handle text/plain from TradingView
    try:
        body = await request.body()
        data_dict = json.loads(body)
        signal = Signal(**data_dict) # Validate with Pydantic
    except Exception as e:
        print(f"❌ Error parsing JSON: {e}")
        raise HTTPException(status_code=422, detail="Invalid JSON format")

    data = signal.dict()
    data["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data["date"] = datetime.now().strftime("%Y-%m-%d") # Store as string for consistency

    # Logic to handle Trade Updates (Win/Loss) vs New Signals
    if signal.action.lower() in ["buy", "sell"]:
        # New Trade
        signals.insert(0, data)
        stats["total_trades"] += 1
        
        # Keep only last 100 signals
        if len(signals) > 100:
            signals.pop()
            
    elif signal.action.lower() == "win":
        stats["wins"] += 1
    elif signal.action.lower() == "loss":
        stats["losses"] += 1
        
    # Recalculate Win Rate
    total_closed = stats["wins"] + stats["losses"]
    if total_closed > 0:
        stats["win_rate"] = (stats["wins"] / total_closed) * 100
    else:
        stats["win_rate"] = 0.0

    # --- FORWARD TO GOOGLE SHEET (Save & Telegram) ---
    if signal.chat_id and signal.text:
        try:
            # We send the same payload to GAS. 
            # GAS will now: 1. Save to Sheet, 2. Forward to Telegram
            requests.post(GAS_URL, json=data)
            print("✅ Forwarded to Google Sheet & Telegram")
        except Exception as e:
            print(f"❌ Failed to forward to GAS: {e}")
    # -------------------------------------------

    return {"status": "success", "message": "Signal received"}

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    # Recalculate today's trades on refresh
    today_str = date.today().strftime("%Y-%m-%d")
    today_count = sum(1 for s in signals if s.get("date") == today_str)
    stats["today_trades"] = today_count

    return templates.TemplateResponse("index.html", {"request": request, "signals": signals, "stats": stats})

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
