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
# MOTOR DE VOZ
# ==========================================
class VoiceEngine:
    def __init__(self):
        try:
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', 160)
            self.engine.setProperty('volume', 1.0)
        except: self.engine = None
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
# CLIENTE DE DERIV
# ==========================================
class DerivClient:
    def __init__(self, token, on_tick_cb, on_auth_cb, log_cb, on_result_cb):
        self.token = token
        self.on_tick = on_tick_cb
        self.on_auth = on_auth_cb
        self.log = log_cb
        self.on_result = on_result_cb
        self.ws = None
        self.connected = False
        self.current_subscription = None

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
            tick = data["tick"]
            if tick.get("symbol") == self.current_subscription:
                self.on_tick(tick)

        if "buy" in data:
            if "error" in data:
                self.log(f"❌ ERROR: {data['error']['message']}")
            else:
                self.log(f"✅ ORDEN LANZADA: {data['buy']['contract_id']}")
                self.ws.send(json.dumps({"proposal_open_contract": 1, "contract_id": data['buy']['contract_id'], "subscribe": 1}))

        if "proposal_open_contract" in data:
            contract = data["proposal_open_contract"]
            if contract.get("is_sold"):
                profit = float(contract.get("profit", 0))
                self.on_result(profit)

    def _on_error(self, ws, error): self.log(f"⚠️ Error WS: {error}")
    def _on_close(self, ws, a, b): self.connected = False

    def subscribe(self, symbol):
        if not self.ws or not self.connected: return
        if self.current_subscription:
            self.ws.send(json.dumps({"forget_all": "ticks"}))
        self.current_subscription = symbol
        self.ws.send(json.dumps({"ticks": symbol, "subscribe": 1}))

    def unsubscribe(self):
        if self.ws and self.current_subscription:
            self.ws.send(json.dumps({"forget_all": "ticks"}))
            self.current_subscription = None

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
# APP UNIFICADA (GUI)
# ==========================================
class SilentEngineApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SILENT ENGINE V2 - AI TRADING")
        self.root.geometry("500x950")
        self.root.configure(bg=COLORS["bg"])

        self.voice = VoiceEngine()
        self.client = None
        self.prices = []
        self.running = False
        self.total_profit = 0
        self.last_signal = ""
        self.last_trade_time = 0
        self.current_signal = None

        self.show_login()

    def clear_screen(self):
        for w in self.root.winfo_children(): w.destroy()

    def show_login(self):
        self.clear_screen()
        f = tk.Frame(self.root, bg=COLORS["bg"], pady=80)
        f.pack(expand=True, fill="both")
        tk.Label(f, text="NEURAL ACCESS", font=("Courier", 24, "bold"), fg=COLORS["accent"], bg=COLORS["bg"]).pack(pady=30)
        tk.Label(f, text="ENTER IP TOKEN", font=("Arial", 10), fg=COLORS["gray"], bg=COLORS["bg"]).pack()
        self.t_entry = tk.Entry(f, font=("Arial", 12), bg="#1a1a24", fg="white", width=35, relief="flat", show="*")
        self.t_entry.pack(pady=10, ipady=10)
        tk.Button(f, text="INITIATE SESSION", command=self.do_login, bg=COLORS["accent"], fg="black", font=("Arial", 11, "bold"), width=25, relief="flat").pack(pady=40, ipady=10)

    def do_login(self):
        token = self.t_entry.get()
        if token:
            self.client = DerivClient(token, self.on_tick, self.on_auth, self.log_msg, self.on_trade_result)
            self.client.connect()

    def on_auth(self, ok, info):
        if ok:
            self.root.after(0, self.show_dash)
            self.voice.speak("Sesión iniciada. Motor neural en línea.")
        else:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Fallo: {info}"))

    def log_msg(self, msg):
        self.root.after(0, lambda: self.log_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} {msg}\n"))
        self.root.after(0, lambda: self.log_text.see(tk.END))

    def show_dash(self):
        self.clear_screen()
        top = tk.Frame(self.root, bg=COLORS["bg"], padx=20, pady=10)
        top.pack(fill="x")
        tk.Label(top, text="SILENT ENGINE V2", font=("Courier", 12, "bold"), fg=COLORS["accent"], bg=COLORS["bg"]).pack(side="left")
        self.profit_label = tk.Label(top, text="Profit: $0.00", font=("Arial", 10, "bold"), fg=COLORS["green"], bg=COLORS["bg"])
        self.profit_label.pack(side="right")

        self.chart_f = tk.Frame(self.root, bg=COLORS["card"], bd=1, relief="solid")
        self.chart_f.pack(padx=20, pady=10, fill="both", expand=True)
        self.setup_chart()

        self.sig_label = tk.Label(self.root, text="SCANNING...", font=("Arial", 22, "bold"), fg=COLORS["green"], bg=COLORS["bg"], pady=10)
        self.sig_label.pack()

        # Manual Trade Buttons
        m_frame = tk.Frame(self.root, bg=COLORS["bg"])
        m_frame.pack(fill="x", padx=20, pady=5)
        self.buy_btn = tk.Button(m_frame, text="BUY ⬆️", command=lambda: self.manual_trade("BUY"), bg=COLORS["green"], fg="black", font=("Arial", 10, "bold"), width=20, state="disabled")
        self.buy_btn.pack(side="left", padx=5, expand=True, fill="x")
        self.sell_btn = tk.Button(m_frame, text="SELL ⬇️", command=lambda: self.manual_trade("SELL"), bg=COLORS["red"], fg="black", font=("Arial", 10, "bold"), width=20, state="disabled")
        self.sell_btn.pack(side="right", padx=5, expand=True, fill="x")

        cfg = tk.Frame(self.root, bg=COLORS["bg"], padx=20)
        cfg.pack(fill="x")

        tk.Label(cfg, text="STAKE ($):", fg=COLORS["gray"], bg=COLORS["bg"]).pack(anchor="w")
        self.s_entry = tk.Entry(cfg, font=("Arial", 11), bg="#1a1a24", fg="white", relief="flat")
        self.s_entry.insert(0, "10")
        self.s_entry.pack(fill="x", pady=2)

        tk.Label(cfg, text="PÉRDIDA MÁX ($):", fg=COLORS["gray"], bg=COLORS["bg"]).pack(anchor="w")
        self.l_entry = tk.Entry(cfg, font=("Arial", 11), bg="#1a1a24", fg="white", relief="flat")
        self.l_entry.insert(0, "100")
        self.l_entry.pack(fill="x", pady=2)

        self.i_combo = ttk.Combobox(cfg, values=list(VOLATILITY_INDICES.keys()), state="readonly")
        self.i_combo.current(4)
        self.i_combo.pack(fill="x", pady=5)

        self.m_combo = ttk.Combobox(cfg, values=["MANUAL", "AUTOMÁTICO"], state="readonly")
        self.m_combo.current(0)
        self.m_combo.pack(fill="x", pady=5)

        self.btn = tk.Button(self.root, text="START NEURAL SCAN", command=self.toggle, bg=COLORS["card"], fg=COLORS["accent"], font=("Arial", 12, "bold"))
        self.btn.pack(fill="x", padx=40, pady=10, ipady=10)

        self.log_text = tk.Text(self.root, height=5, bg=COLORS["card"], fg=COLORS["text"], font=("Arial", 8), relief="flat")
        self.log_text.pack(fill="x", padx=20, pady=5)

    def setup_chart(self):
        self.fig, self.ax = plt.subplots(figsize=(5, 3), facecolor=COLORS["card"])
        self.ax.set_facecolor(COLORS["card"])
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.chart_f)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def toggle(self):
        if not self.running:
            self.running = True
            self.prices = [] # Reset prices on new symbol
            self.btn.config(text="STOP SCAN", fg=COLORS["red"])
            self.buy_btn.config(state="normal")
            self.sell_btn.config(state="normal")
            self.client.subscribe(VOLATILITY_INDICES[self.i_combo.get()])
            self.voice.speak(f"Iniciando escaneo neural en {self.i_combo.get()}.")
        else:
            self.running = False
            self.btn.config(text="START NEURAL SCAN", fg=COLORS["accent"])
            self.buy_btn.config(state="disabled")
            self.sell_btn.config(state="disabled")
            self.client.unsubscribe()
            self.voice.speak("Sistema pausado.")

    def manual_trade(self, side):
        try:
            stake = float(self.s_entry.get() or 10)
            self.client.execute_trade(VOLATILITY_INDICES[self.i_combo.get()], side, stake)
        except: messagebox.showerror("Error", "Stake inválido")

    def on_tick(self, tick):
        if not self.running: return
        p = float(tick["bid"])
        self.prices.append(p)
        if len(self.prices) > 60: self.prices.pop(0)
        self.root.after(0, self.update_ui, p)

    def update_ui(self, p):
        self.ax.clear()
        self.ax.plot(self.prices, color=COLORS["accent"])
        self.ax.set_facecolor(COLORS["card"])
        self.canvas.draw()

        if len(self.prices) >= 25:
            df = pd.DataFrame({'close': self.prices})
            rsi = RSIIndicator(df['close']).rsi().iloc[-1]
            bb_h = BollingerBands(df['close']).bollinger_hband().iloc[-1]
            bb_l = BollingerBands(df['close']).bollinger_lband().iloc[-1]
            macd = MACD(df['close']).macd().iloc[-1]
            macd_s = MACD(df['close']).macd_signal().iloc[-1]

            score_buy = 0
            score_sell = 0

            if rsi < 32: score_buy += 35
            elif rsi > 68: score_sell += 35

            if p <= bb_l: score_buy += 30
            elif p >= bb_h: score_sell += 30

            if macd > macd_s: score_buy += 25
            elif macd < macd_s: score_sell += 25

            sig = "HOLD"
            if score_buy >= 60: sig = "BUY"
            elif score_sell >= 60: sig = "SELL"

            label = f"STRONG {sig} ⬆️" if sig == "BUY" else (f"STRONG {sig} ⬇️" if sig == "SELL" else "SCANNING...")
            color = COLORS["green"] if sig == "BUY" else (COLORS["red"] if sig == "SELL" else COLORS["accent"])

            if self.last_signal != label:
                self.sig_label.config(text=label, fg=color)
                if sig != "HOLD":
                    self.voice.speak(f"Señal detectada: {sig}")
                    if self.m_combo.get() == "AUTOMÁTICO": self.do_trade(sig)
                self.last_signal = label

    def do_trade(self, side):
        now = time.time()
        if now - self.last_trade_time > 15:
            try:
                stake = float(self.s_entry.get() or 10)
                self.client.execute_trade(VOLATILITY_INDICES[self.i_combo.get()], side, stake)
                self.last_trade_time = now
            except: pass

    def on_trade_result(self, profit):
        self.total_profit += profit
        self.root.after(0, self.update_profit_display)
        msg = f"Operación cerrada. {'Ganancia' if profit > 0 else 'Pérdida'}: {abs(profit):.2f} dólares."
        self.voice.speak(msg)

        try:
            max_loss = float(self.l_entry.get() or 100)
            if self.total_profit <= -max_loss:
                self.root.after(0, self.stop_on_loss)
        except: pass

    def update_profit_display(self):
        c = COLORS["green"] if self.total_profit >= 0 else COLORS["red"]
        self.profit_label.config(text=f"Profit: ${self.total_profit:.2f}", fg=c)

    def stop_on_loss(self):
        self.toggle() # Stop everything
        messagebox.showinfo("Stop Loss", "Límite de pérdida alcanzado. El bot se ha detenido por seguridad.")

if __name__ == "__main__":
    root = tk.Tk()
    root.resizable(False, False)
    app = SilentEngineApp(root)
    root.mainloop()
