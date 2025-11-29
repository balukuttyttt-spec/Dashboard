from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from datetime import datetime, date
import uvicorn
import os
import requests

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
    "wins": 0,       # Changed from total_wins
    "losses": 0,     # Changed from total_losses
    "win_rate": 0.0  # Changed from winrate
}

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

@app.post("/webhook")
async def webhook(signal: Signal):
    data = signal.dict()
    data["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data["date"] = datetime.now().date()

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

    # --- FORWARD TO TELEGRAM (Google Script) ---
    # Replace with your Google Apps Script URL if you have one
    TELEGRAM_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxO5tLxWjDRLwj9WRPtM3Fszm0WxC5CI5WEWNADs1CkpfFccURZGtOps5pWuABeUfg/exec"
    
    if signal.chat_id and signal.text:
        try:
            telegram_payload = {
                "chat_id": signal.chat_id,
                "text": signal.text
            }
            requests.post(TELEGRAM_SCRIPT_URL, json=telegram_payload)
            print("✅ Forwarded to Telegram")
        except Exception as e:
            print(f"❌ Failed to forward to Telegram: {e}")
    # -------------------------------------------

    return {"status": "success", "message": "Signal received"}

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    # Recalculate today's trades on refresh
    today_count = sum(1 for s in signals if s.get("date") == date.today())
    stats["today_trades"] = today_count

    return templates.TemplateResponse("index.html", {"request": request, "signals": signals, "stats": stats})

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
