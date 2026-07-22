"""
bot.py — MT5 trading bot logic.

This file is GitHub-agnostic. It reads connection details from environment
variables so it can run the same way locally, on a VPS, or in CI.

Env vars required:
    MT5_LOGIN     - your MT5 account number
    MT5_PASSWORD  - your MT5 account password
    MT5_SERVER    - your broker's server name (must match MT5 terminal exactly)

Optional env vars:
    MT5_PATH      - path to terminal64.exe (defaults to standard Windows install path)
    MAX_MINUTES   - how long the bot should run before stopping itself (default 230)
    SYMBOL        - instrument to trade (default "EURUSD")
"""

import os
import sys
import time
import logging
from datetime import datetime, timedelta

import MetaTrader5 as mt5

# ---------- Config ----------

LOGIN = 91317119
PASSWORD = "XENDERLOGIN8$y"  
SERVER = "LiteFinance-MT5-Demo"
(File > Login)
TERMINAL_PATH = os.environ.get("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")
MAX_MINUTES = int(os.environ.get("MAX_MINUTES", "230"))  # stop before GitHub's 6hr hard kill
SYMBOL = os.environ.get("SYMBOL", "EURUSD")
LOT_SIZE = 0.01
CHECK_INTERVAL_SECONDS = 30

# ---------- Logging ----------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot_run.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("mt5bot")


def connect():
    if not mt5.initialize(path=TERMINAL_PATH, login=LOGIN, password=PASSWORD,
                           server=SERVER, timeout=60000, portable=True):
        log.error("initialize() failed: %s", mt5.last_error())
        raise SystemExit(1)

    account = mt5.account_info()
    if account is None:
        log.error("account_info() failed: %s", mt5.last_error())
        raise SystemExit(1)

    log.info("Connected to account %s on %s | balance: %s %s",
              account.login, account.server, account.balance, account.currency)


def get_signal():
    """
    Placeholder strategy logic. Replace this with your actual signal.
    Return "buy", "sell", or None.
    """
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 3)
    if rates is None or len(rates) < 3:
        return None

    closes = [r["close"] for r in rates]
    if closes[-1] > closes[-2] > closes[-3]:
        return "buy"
    elif closes[-1] < closes[-2] < closes[-3]:
        return "sell"
    return None


def place_order(direction):
    symbol_info = mt5.symbol_info(SYMBOL)
    if symbol_info is None:
        log.warning("Symbol %s not found", SYMBOL)
        return

    if not symbol_info.visible:
        mt5.symbol_select(SYMBOL, True)

    price = mt5.symbol_info_tick(SYMBOL).ask if direction == "buy" else mt5.symbol_info_tick(SYMBOL).bid
    order_type = mt5.ORDER_TYPE_BUY if direction == "buy" else mt5.ORDER_TYPE_SELL

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": LOT_SIZE,
        "type": order_type,
        "price": price,
        "deviation": 10,
        "magic": 123456,
        "comment": "github-actions-bot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        log.warning("Order failed: %s", result)
    else:
        log.info("Order placed: %s %s @ %s", direction, SYMBOL, price)


def close_all_positions():
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions:
        return
    for pos in positions:
        direction = "sell" if pos.type == mt5.ORDER_TYPE_BUY else "buy"
        price = mt5.symbol_info_tick(SYMBOL).bid if direction == "sell" else mt5.symbol_info_tick(SYMBOL).ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": pos.volume,
            "type": mt5.ORDER_TYPE_SELL if direction == "sell" else mt5.ORDER_TYPE_BUY,
            "position": pos.ticket,
            "price": price,
            "deviation": 10,
            "magic": 123456,
            "comment": "github-actions-bot-close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        log.info("Closed position %s -> retcode %s", pos.ticket, result.retcode)


def main():
    connect()
    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=MAX_MINUTES)
    log.info("Bot starting. Will auto-stop at %s (max %s minutes)", end_time, MAX_MINUTES)

    try:
        while datetime.now() < end_time:
            signal = get_signal()
            if signal:
                log.info("Signal: %s", signal)
                place_order(signal)
            else:
                log.info("No signal this cycle")

            time.sleep(CHECK_INTERVAL_SECONDS)

    except Exception:
        log.exception("Bot crashed with an unhandled exception")

    finally:
        log.info("Time limit reached or bot stopping — closing open positions")
        close_all_positions()
        mt5.shutdown()
        log.info("MT5 shutdown complete. Run finished.")


if __name__ == "__main__":
    main()
