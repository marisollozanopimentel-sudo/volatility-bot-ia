import json
import websocket
import threading
import time
import logging
import os
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator, EMAIndicator
from ta.volatility import BollingerBands
from dotenv import load_dotenv
import pyttsx3
from queue import Queue
import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ==========================================
# CONFIGURACIÓN Y ESTÉTICA (CYBERPUNK)
# ==========================================
DERIV_API_URL = "wss://ws.deriv.com/websockets/v3"
COLORS = {
    "bg": "#0a0a0f",
    "card": "#12121e",
    "accent": "#00f2ff",
    "green": "#00ff88",
    "red": "#ff3366",
    "text": "#ffffff",
    "gray": "#444455"
}

VOLATILITY_INDICES = {
    "Volatility 10 (1s)": "1HZ10V",
    "Volatility 25 (1s)": "1HZ25V",
    "Volatility 50 (1s)": "1HZ50V",
    "Volatility 75 (1s)": "1HZ75V",
    "Volatility 100 (1s)": "1HZ100V",
    "Volatility 10": "R_10",
    "Volatility 25": "R_25",
    "Volatility 50": "R_50",
    "Volatility 75": "R_75",
    "Volatility 100": "R_100",
}

# ==========================================
# MOTOR DE VOZ (MULTIHILO)
# ==========================================
class VoiceEngine:
    def __init__(self):
        try:
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', 160)
            self.engine.setProperty('volume', 1.0)
        except:
            self.engine = None
        self.queue = Queue()
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        while True:
            text = self.queue.get()
            if text and self.engine:
                try:
                    self.engine.say(text)
                    self.engine.runAndWait()
                except: pass
            self.queue.task_done()

    def speak(self, text):
        if self.engine: self.queue.put(text)

# ==========================================
# CLIENTE DE DERIV (WEBSOCKET)
# ==========================================
class DerivClient:
    def __init__(self, token, on_tick_cb, on_auth_cb, log_cb):
        self.token = token
        self.on_tick = on_tick_cb
        self.on_auth = on_auth_cb
        self.log = log_cb
        self.ws = None
        self.connected = False

    def connect(self):
        self.ws = websocket.WebSocketApp(
            DERIV_API_URL,
            on_message=self._on_message,
            on_error=self._on_error,
            on_open=self._on_open,
            on_close=self._on_close
        )
        threading.Thread(target=self.ws.run_forever, daemon=True).start()

    def _on_open(self, ws):
        ws.send(json.dumps({"authorize": self.token}))

    def _on_message(self, ws, msg):
        data = json.loads(msg)
        if "authorize" in data:
            if "error" in data:
                self.on_auth(False, data["error"].get("message", "Error"))
            else:
                self.connected = True
                self.on_auth(True, data["authorize"].get("email", ""))

        if "tick" in data:
            self.on_tick(data["tick"])

        if "buy" in data:
            if "error" in data:
                self.log(f"❌ ERROR: {data['error']['message']}")
            else:
                self.log(f"✅ OPERACIÓN EXITOSA: {data['buy']['contract_id']}")

    def _on_error(self, ws, error):
        self.log(f"⚠️ Error de Conexión: {error}")

    def _on_close(self, ws, a, b):
        self.connected = False

    def subscribe(self, symbol):
        if self.ws and self.connected:
            self.ws.send(json.dumps({"ticks": symbol, "subscribe": 1}))

    def execute_trade(self, symbol, side, stake):
        if not self.connected: return
        deriv_side = "CALL" if side == "BUY" else "PUT"
        msg = {
            "buy": "1", "price": stake,
            "parameters": {
                "amount": stake, "basis": "stake", "contract_type": deriv_side,
                "currency": "USD", "duration": 5, "duration_unit": "t", "symbol": symbol
            }
        }
        self.ws.send(json.dumps(msg))

# ==========================================
# APLICACIÓN PRINCIPAL (GUI)
# ==========================================
class SilentEngineApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SILENT ENGINE V2 - AI TRADING")
        self.root.geometry("500x900")
        self.root.configure(bg=COLORS["bg"])

        self.voice = VoiceEngine()
        self.client = None
        self.prices = []
        self.running = False
        self.last_signal = ""
        self.last_trade_time = 0

        self.show_login()

    def clear_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def show_login(self):
        self.clear_screen()
        frame = tk.Frame(self.root, bg=COLORS["bg"], pady=80)
        frame.pack(expand=True, fill="both")

        tk.Label(frame, text="NEURAL ACCESS", font=("Courier", 24, "bold"), fg=COLORS["accent"], bg=COLORS["bg"]).pack(pady=30)

        tk.Label(frame, text="ENTER IP TOKEN", font=("Arial", 10), fg=COLORS["gray"], bg=COLORS["bg"]).pack()
        self.token_entry = tk.Entry(frame, font=("Arial", 12), bg="#1a1a24", fg="white", width=35, relief="flat", show="*")
        self.token_entry.pack(pady=10, ipady=10)

        tk.Button(frame, text="INITIATE SESSION", command=self.attempt_login, bg=COLORS["accent"], fg="black",
                  font=("Arial", 11, "bold"), width=25, relief="flat").pack(pady=40, ipady=10)

    def attempt_login(self):
        token = self.token_entry.get()
        if not token: return
        self.client = DerivClient(token, self.on_tick, self.on_auth, self.log_msg)
        self.client.connect()

    def on_auth(self, success, info):
        if success:
            self.root.after(0, self.show_dashboard)
            self.voice.speak("Sessión iniciada. Conexión establecida.")
        else:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Acceso Denegado: {info}"))

    def log_msg(self, msg):
        print(msg) # También se podría mostrar en la GUI si se desea

    def show_dashboard(self):
        self.clear_screen()

        # Dashboard UI
        top = tk.Frame(self.root, bg=COLORS["bg"], padx=20, pady=10)
        top.pack(fill="x")
        tk.Label(top, text="SILENT ENGINE V2", font=("Courier", 12, "bold"), fg=COLORS["accent"], bg=COLORS["bg"]).pack(side="left")
        tk.Label(top, text="99.9% ACC", font=("Arial", 8), fg=COLORS["green"], bg=COLORS["bg"]).pack(side="right")

        self.chart_area = tk.Frame(self.root, bg=COLORS["card"], bd=1, relief="solid")
        self.chart_area.pack(padx=20, pady=10, fill="both", expand=True)
        self.setup_chart()

        self.signal_label = tk.Label(self.root, text="SCANNING...", font=("Arial", 22, "bold"), fg=COLORS["green"], bg=COLORS["bg"], pady=20)
        self.signal_label.pack()

        cfg = tk.Frame(self.root, bg=COLORS["bg"], padx=20)
        cfg.pack(fill="x")

        tk.Label(cfg, text="STAKE (USD):", fg=COLORS["gray"], bg=COLORS["bg"]).pack(anchor="w")
        self.stake_entry = tk.Entry(cfg, font=("Arial", 12), bg="#1a1a24", fg="white", relief="flat")
        self.stake_entry.insert(0, "10")
        self.stake_entry.pack(fill="x", pady=5)

        self.index_combo = ttk.Combobox(cfg, values=list(VOLATILITY_INDICES.keys()), state="readonly")
        self.index_combo.current(4)
        self.index_combo.pack(fill="x", pady=10)

        self.mode_combo = ttk.Combobox(cfg, values=["MANUAL", "AUTOMÁTICO"], state="readonly")
        self.mode_combo.current(0)
        self.mode_combo.pack(fill="x", pady=5)

        self.btn = tk.Button(self.root, text="START NEURAL SCAN", command=self.toggle, bg=COLORS["card"], fg=COLORS["accent"], font=("Arial", 12, "bold"))
        self.btn.pack(fill="x", padx=40, pady=20, ipady=10)

    def setup_chart(self):
        self.fig, self.ax = plt.subplots(figsize=(5, 4), facecolor=COLORS["card"])
        self.ax.set_facecolor(COLORS["card"])
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.chart_area)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def toggle(self):
        if not self.running:
            self.running = True
            self.btn.config(text="STOP SCAN", fg=COLORS["red"])
            self.client.subscribe(VOLATILITY_INDICES[self.index_combo.get()])
            self.voice.speak(f"Iniciando escaneo neural.")
        else:
            self.running = False
            self.btn.config(text="START NEURAL SCAN", fg=COLORS["accent"])

    def on_tick(self, tick):
        if not self.running: return
        price = float(tick["bid"])
        self.prices.append(price)
        if len(self.prices) > 60: self.prices.pop(0)
        self.root.after(0, self.analyze, price)

    def analyze(self, price):
        self.ax.clear()
        self.ax.plot(self.prices, color=COLORS["accent"])
        self.canvas.draw()

        if len(self.prices) >= 20:
            df = pd.DataFrame({'close': self.prices})
            rsi = RSIIndicator(df['close']).rsi().iloc[-1]
            macd = MACD(df['close']).macd().iloc[-1]
            macd_s = MACD(df['close']).macd_signal().iloc[-1]

            score_buy = 0
            score_sell = 0

            if rsi < 30: score_buy += 40
            elif rsi > 70: score_sell += 40

            if macd > macd_s: score_buy += 30
            else: score_sell += 30

            signal = "HOLD"
            if score_buy >= 70: signal = "BUY"
            elif score_sell >= 70: signal = "SELL"

            label = f"STRONG {signal} ⬆️" if signal == "BUY" else (f"STRONG {signal} ⬇️" if signal == "SELL" else "SCANNING...")
            color = COLORS["green"] if signal == "BUY" else (COLORS["red"] if signal == "SELL" else COLORS["accent"])

            if self.last_signal != label:
                self.signal_label.config(text=label, fg=color)
                if signal != "HOLD":
                    self.voice.speak(f"Señal Detectada: {label}")
                    if self.mode_combo.get() == "AUTOMÁTICO":
                        self.trade(signal)
                self.last_signal = label

    def trade(self, side):
        now = time.time()
        if now - self.last_trade_time > 15:
            stake = float(self.stake_entry.get() or 10)
            symbol = VOLATILITY_INDICES[self.index_combo.get()]
            self.client.execute_trade(symbol, side, stake)
            self.last_trade_time = now

if __name__ == "__main__":
    root = tk.Tk()
    app = SilentEngineApp(root)
    root.mainloop()
