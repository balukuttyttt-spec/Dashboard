from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from datetime import datetime, date
import uvicorn

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# In-memory storage
signals = []
stats = {
    "total_trades": 0,
    "today_trades": 0,
    "total_wins": 0,
    "total_losses": 0,
    "winrate": 0.0
}

class Signal(BaseModel):
    action: str
    ticker: str
    price: float
    sl: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    tp3: float = 0.0
    # Optional fields for updates
    result: str = None # "win" or "loss"
    comment: str = None

@app.post("/webhook")
async def webhook(signal: Signal):
    """
    Endpoint to receive TradingView Alerts.
    """
    data = signal.dict()
    data["time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data["date"] = datetime.now().date()
    
    # Logic to handle Trade Updates (Win/Loss) vs New Signals
    if signal.action in ["buy", "sell"]:
        # New Trade
        signals.insert(0, data)
        stats["total_trades"] += 1
        if data["date"] == date.today():
            stats["today_trades"] += 1
            
    elif signal.action in ["win", "loss", "tp", "sl"]:
        # Update Stats (Simplified logic: assumes alert sends 'win' or 'loss')
        if signal.action == "win" or signal.action == "tp":
            stats["total_wins"] += 1
        elif signal.action == "loss" or signal.action == "sl":
            stats["total_losses"] += 1
            
    # Recalculate Winrate
    if (stats["total_wins"] + stats["total_losses"]) > 0:
        stats["winrate"] = round((stats["total_wins"] / (stats["total_wins"] + stats["total_losses"])) * 100, 2)
    
    # Keep only last 50 signals
    if len(signals) > 50:
        signals.pop()
        
    print(f"Received Signal: {data}")
    return {"status": "success", "message": "Signal received"}

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """
    Render the Dashboard UI.
    """
    # Recalculate today's trades on refresh (in case date changed)
    today_count = sum(1 for s in signals if s.get("date") == date.today())
    stats["today_trades"] = today_count
    
    return templates.TemplateResponse("index.html", {"request": request, "signals": signals, "stats": stats})

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
