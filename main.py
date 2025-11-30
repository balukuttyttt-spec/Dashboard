
from fastapi import FastAPI, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
import requests
import json
import logging

# --- CONFIGURATION ---
# 1. Google Apps Script URL (For Saving to Sheet & Telegram)
GAS_URL = "https://script.google.com/macros/s/AKfycbzmoFvNtRZgc2t6zRaLmtlPibmEIJgyaXsWC0hgKuLUNhFwKeCiT6LquLyzcZ7hAyOv/exec"

# 2. Telegram Chat ID (Fallback if not in signal)
DEFAULT_CHAT_ID = "-1003048841522"

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Store stats in memory
stats = {
    "total_trades": 0,
    "today_trades": 0,
    "wins": 0,       # Changed from total_wins
    "losses": 0,     # Changed from total_losses
    "win_rate": 0.0  # Changed from winrate
}

# Store recent signals
signals = []

class Signal(BaseModel):
    action: str
    ticker: str
    price: float
    sl: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    tp3: float = 0.0
    # Optional fields
    date: str = None
    time: str = None
    chat_id: str = None
    text: str = None

@app.on_event("startup")
async def startup_event():
    # Fetch history from Google Sheet on startup
    try:
        logger.info("Fetching history from Google Sheet...")
        response = requests.get(GAS_URL)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                # Update signals
                global signals
                signals = data.get("data", [])
                logger.info(f"Loaded {len(signals)} past trades.")
                
                # Recalculate stats
                wins = sum(1 for s in signals if s.get("status") == "WIN")
                losses = sum(1 for s in signals if s.get("status") == "LOSS")
                total = len(signals)
                
                stats["total_trades"] = total
                stats["wins"] = wins
                stats["losses"] = losses
                stats["win_rate"] = (wins / total * 100) if total > 0 else 0.0
    except Exception as e:
        logger.error(f"Failed to fetch history: {e}")

@app.get("/", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "stats": stats,
        "signals": signals
    })

@app.post("/webhook")
async def receive_signal(request: Request):
    try:
        # 1. Parse JSON manually to handle text/plain content type
        body_bytes = await request.body()
        try:
            payload = json.loads(body_bytes)
        except json.JSONDecodeError:
            # Try parsing as string if it's not pure JSON bytes
            payload = json.loads(body_bytes.decode('utf-8'))
            
        # 2. Convert to Signal object
        signal = Signal(**payload)
        
        # 3. Add Timestamp if missing
        import datetime
        now = datetime.datetime.now()
        if not signal.date:
            signal.date = now.strftime("%Y-%m-%d")
        if not signal.time:
            signal.time = now.strftime("%H:%M:%S")

        # 4. Update Stats
        stats["total_trades"] += 1
        stats["today_trades"] += 1
        
        # 5. Add to Local List
        signal_dict = signal.dict()
        signals.insert(0, signal_dict)
        
        # Keep only last 50
        if len(signals) > 50:
            signals.pop()
            
        logger.info(f"Signal Received: {signal.ticker} {signal.action}")

        # --- FORWARD TO GOOGLE SHEET (Save & Telegram) ---
        # Logic: If chat_id/text is missing (Auto-Trade JSON), we construct it.
        
        forward_data = signal_dict.copy()
        
        # A. Fix Chat ID
        if not forward_data.get("chat_id"):
            forward_data["chat_id"] = DEFAULT_CHAT_ID
            
        # B. Fix Text (Construct Message)
        if not forward_data.get("text"):
            # Create a nice HTML message for Telegram
            emoji = "🟢" if "buy" in signal.action.lower() else "🔴"
            forward_data["text"] = (
                f"{emoji} <b>SIGNAL RECEIVED</b>\n"
                f"<b>Ticker:</b> {signal.ticker}\n"
                f"<b>Action:</b> {signal.action}\n"
                f"<b>Price:</b> {signal.price}\n"
                f"<b>TP1:</b> {signal.tp1} | <b>TP2:</b> {signal.tp2} | <b>TP3:</b> {signal.tp3}\n"
                f"<b>SL:</b> {signal.sl}"
            )

        try:
            logger.info(f"Forwarding to GAS: {forward_data['ticker']}")
            requests.post(GAS_URL, json=forward_data)
            logger.info("✅ Forwarded to Google Sheet & Telegram")
        except Exception as e:
            logger.error(f"❌ Failed to forward to GAS: {e}")

        return {"status": "success", "message": "Signal received"}

    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=422, detail=str(e))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
