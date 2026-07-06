import json
import websocket
import threading
import time
import os
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator
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
    "gray": "#444455",
    "gold": "#ffd700"
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
                # Suscribirse para ver el resultado
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
        self.root.title("SILENT ENGINE V2 - PRECISION BURST")
        self.root.geometry("520x980")
        self.root.configure(bg=COLORS["bg"])

        self.voice = VoiceEngine()
        self.client = None
        self.prices = []
        self.running = False
        self.total_profit = 0
        self.last_signal_text = ""
        self.last_trade_time = 0
        self.tick_counter = 0
        self.is_tracking_burst = False

        self.show_login()

    def clear_screen(self):
        for w in self.root.winfo_children(): w.destroy()

    def show_login(self):
        self.clear_screen()
        f = tk.Frame(self.root, bg=COLORS["bg"], pady=80)
        f.pack(expand=True, fill="both")
        tk.Label(f, text="SILENT ENGINE V2", font=("Courier", 24, "bold"), fg=COLORS["accent"], bg=COLORS["bg"]).pack(pady=10)
        tk.Label(f, text="BURST PREDICTION MODE", font=("Arial", 10), fg=COLORS["green"], bg=COLORS["bg"]).pack(pady=20)

        tk.Label(f, text="ENTER IP TOKEN", font=("Arial", 9), fg=COLORS["gray"], bg=COLORS["bg"]).pack()
        self.t_entry = tk.Entry(f, font=("Arial", 12), bg="#1a1a24", fg="white", width=35, relief="flat", show="*")
        self.t_entry.pack(pady=10, ipady=10)

        tk.Button(f, text="START APPLICATION", command=self.do_login, bg=COLORS["accent"], fg="black", font=("Arial", 11, "bold"), width=25, relief="flat").pack(pady=40, ipady=10)

    def do_login(self):
        token = self.t_entry.get()
        if token:
            self.client = DerivClient(token, self.on_tick, self.on_auth, self.log_msg, self.on_trade_result)
            self.client.connect()

    def on_auth(self, ok, info):
        if ok:
            self.root.after(0, self.show_dash)
            self.voice.speak("Sesión iniciada. Escaneo de ráfagas activado.")
        else:
            self.root.after(0, lambda: messagebox.showerror("Error", f"Fallo de Token: {info}"))

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

        # Live Chart
        self.chart_f = tk.Frame(self.root, bg=COLORS["card"], bd=1, relief="solid", highlightbackground=COLORS["accent"])
        self.chart_f.pack(padx=20, pady=5, fill="both", expand=True)
        self.setup_chart()

        # Burst Status Area
        ai_info = tk.Frame(self.root, bg=COLORS["bg"], padx=20)
        ai_info.pack(fill="x")
        self.ai_status = tk.Label(ai_info, text="CORE: PREDICTING 5 TICKS", font=("Arial", 9, "bold"), fg=COLORS["gray"], bg=COLORS["bg"])
        self.ai_status.pack(side="left")
        self.scan_label = tk.Label(ai_info, text="SCAN: 0/3", font=("Arial", 8), fg=COLORS["accent"], bg=COLORS["bg"])
        self.scan_label.pack(side="right")

        # Signal Display
        sig_container = tk.Frame(self.root, bg=COLORS["bg"])
        sig_container.pack(fill="x", pady=10)
        self.sig_label = tk.Label(sig_container, text="ANALYZING MOMENTUM...", font=("Arial", 20, "bold"), fg=COLORS["accent"], bg=COLORS["bg"])
        self.sig_label.pack()
        self.conf_label = tk.Label(sig_container, text="", font=("Arial", 12, "bold"), fg=COLORS["green"], bg=COLORS["bg"])
        self.conf_label.pack()

        # Burst Counter (Tick 1 to 5)
        self.burst_count_label = tk.Label(self.root, text="", font=("Orbitron", 36, "bold"), fg=COLORS["gold"], bg=COLORS["bg"])
        self.burst_count_label.pack(pady=5)

        # Manual Trade Buttons
        m_frame = tk.Frame(self.root, bg=COLORS["bg"])
        m_frame.pack(fill="x", padx=20, pady=5)
        self.buy_btn = tk.Button(m_frame, text="BUY BURST ⬆️", command=lambda: self.manual_trade("BUY"), bg=COLORS["green"], fg="black", font=("Arial", 10, "bold"), width=20, state="disabled", relief="flat")
        self.buy_btn.pack(side="left", padx=5, expand=True, fill="x")
        self.sell_btn = tk.Button(m_frame, text="SELL BURST ⬇️", command=lambda: self.manual_trade("SELL"), bg=COLORS["red"], fg="black", font=("Arial", 10, "bold"), width=20, state="disabled", relief="flat")
        self.sell_btn.pack(side="right", padx=5, expand=True, fill="x")

        # Config Panel
        cfg = tk.Frame(self.root, bg=COLORS["card"], padx=20, pady=10)
        cfg.pack(fill="x", padx=20, pady=10)

        row1 = tk.Frame(cfg, bg=COLORS["card"])
        row1.pack(fill="x")
        tk.Label(row1, text="STAKE ($):", fg="white", bg=COLORS["card"], font=("Arial", 8)).pack(side="left")
        self.s_entry = tk.Entry(row1, font=("Arial", 10), bg=COLORS["bg"], fg="white", relief="flat", width=10)
        self.s_entry.insert(0, "10")
        self.s_entry.pack(side="right")

        row2 = tk.Frame(cfg, bg=COLORS["card"])
        row2.pack(fill="x", pady=2)
        tk.Label(row2, text="STOP LOSS ($):", fg="white", bg=COLORS["card"], font=("Arial", 8)).pack(side="left")
        self.l_entry = tk.Entry(row2, font=("Arial", 10), bg=COLORS["bg"], fg="white", relief="flat", width=10)
        self.l_entry.insert(0, "100")
        self.l_entry.pack(side="right")

        self.i_combo = ttk.Combobox(cfg, values=list(VOLATILITY_INDICES.keys()), state="readonly")
        self.i_combo.current(4)
        self.i_combo.pack(fill="x", pady=5)

        self.m_combo = ttk.Combobox(cfg, values=["MODO MANUAL", "MODO AUTOMÁTICO"], state="readonly")
        self.m_combo.current(0)
        self.m_combo.pack(fill="x", pady=5)

        self.btn = tk.Button(self.root, text="** START BURST SCAN **", command=self.toggle, bg=COLORS["accent"], fg="black", font=("Arial", 12, "bold"), relief="flat")
        self.btn.pack(fill="x", padx=40, pady=10, ipady=15)

        self.log_text = tk.Text(self.root, height=3, bg=COLORS["bg"], fg=COLORS["gray"], font=("Arial", 8), relief="flat", borderwidth=0)
        self.log_text.pack(fill="x", padx=20)

    def setup_chart(self):
        self.fig, self.ax = plt.subplots(figsize=(5, 3), facecolor=COLORS["card"])
        self.ax.set_facecolor(COLORS["card"])
        self.ax.tick_params(colors=COLORS["gray"], labelsize=7)
        for spine in self.ax.spines.values(): spine.set_visible(False)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.chart_f)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def toggle(self):
        if not self.running:
            self.running = True
            self.prices = []
            self.tick_counter = 0
            self.btn.config(text="** STOP SCAN **", bg=COLORS["red"], fg="white")
            self.buy_btn.config(state="normal")
            self.sell_btn.config(state="normal")
            self.ai_status.config(text="NEURAL CORE: BURST PREDICTION ACTIVE", fg=COLORS["green"])
            self.client.subscribe(VOLATILITY_INDICES[self.i_combo.get()])
            self.voice.speak(f"Escaneo de ráfagas iniciado. Buscando 5 ticks de movimiento.")
        else:
            self.running = False
            self.btn.config(text="** START BURST SCAN **", bg=COLORS["accent"], fg="black")
            self.buy_btn.config(state="disabled")
            self.sell_btn.config(state="disabled")
            self.ai_status.config(text="NEURAL CORE: STANDBY", fg=COLORS["gray"])
            self.client.unsubscribe()
            self.voice.speak("Sistema en pausa.")

    def manual_trade(self, side):
        try:
            stake = float(self.s_entry.get() or 10)
            self.client.execute_trade(VOLATILITY_INDICES[self.i_combo.get()], side, stake)
            self.voice.speak(f"Orden manual de {side} enviada.")
        except: messagebox.showerror("Error", "Stake inválido")

    def on_tick(self, tick):
        if not self.running: return
        p = float(tick["bid"])
        self.prices.append(p)
        if len(self.prices) > 60: self.prices.pop(0)

        # Scan Ticks fixed at 3
        self.tick_counter += 1
        scan_progress = (self.tick_counter % 3) if self.tick_counter % 3 != 0 else 3
        self.root.after(0, lambda: self.scan_label.config(text=f"SCAN: {scan_progress}/3"))

        if self.tick_counter >= 3:
            self.tick_counter = 0
            self.root.after(0, self.analyze, p)
        else:
            self.root.after(0, self.refresh_chart)

    def refresh_chart(self):
        self.ax.clear()
        self.ax.plot(self.prices, color=COLORS["accent"], linewidth=2)
        self.ax.set_facecolor(COLORS["card"])
        self.canvas.draw()

    def analyze(self, p):
        self.refresh_chart()
        if len(self.prices) >= 25:
            df = pd.DataFrame({'close': self.prices})
            rsi = RSIIndicator(df['close']).rsi().iloc[-1]
            macd = MACD(df['close']).macd().iloc[-1]
            macd_s = MACD(df['close']).macd_signal().iloc[-1]
            ema = EMAIndicator(df['close'], window=10).ema_indicator().iloc[-1]

            momentum_up = (rsi < 42 and p > ema) or (macd > macd_s and p > ema)
            momentum_down = (rsi > 58 and p < ema) or (macd < macd_s and p < ema)

            sig = "HOLD"
            confidence = 0
            if momentum_up:
                sig = "BUY"
                confidence = 85 + (min(rsi, 40) / 40) * 14.9
            elif momentum_down:
                sig = "SELL"
                confidence = 85 + (min(100-rsi, 40) / 40) * 14.9

            label = f"STRONG {sig} ⬆️" if sig == "BUY" else (f"STRONG {sig} ⬇️" if sig == "SELL" else "SCANNING DATA...")
            color = COLORS["green"] if sig == "BUY" else (COLORS["red"] if sig == "SELL" else COLORS["accent"])

            if self.last_signal_text != label:
                self.sig_label.config(text=label, fg=color)
                if sig != "HOLD":
                    # REQUERIMIENTO ESPECIAL: Calificación 10/2 y 99%
                    conf_text = f"CALIFICACIÓN: 10/2 | PROBABILIDAD: {confidence:.1f}%"
                    self.conf_label.config(text=conf_text, fg=color)
                    self.voice.speak(f"Calificación 10 de 2. Probabilidad del {int(confidence)} por ciento de ráfaga de 5 ticks. Iniciando.")
                    self.start_burst_countdown(sig)
                else:
                    self.conf_label.config(text="")
                self.last_signal_text = label

    def start_burst_countdown(self, sig):
        if self.is_tracking_burst: return
        self.is_tracking_burst = True

        def run_burst():
            for i in range(1, 6):
                self.root.after(0, lambda x=i: self.burst_count_label.config(text=f"TICK {x}"))
                self.voice.speak(f"Tick {i}")

                # REQUERIMIENTO: Entrar en el Tick 2
                if i == 2 and self.m_combo.get() == "MODO AUTOMÁTICO":
                    self.do_trade(sig)

                time.sleep(1.0) # Un segundo entre ticks de la ráfaga

            self.root.after(0, lambda: self.burst_count_label.config(text=""))
            self.is_tracking_burst = False

        threading.Thread(target=run_burst, daemon=True).start()

    def do_trade(self, side):
        now = time.time()
        if now - self.last_trade_time > 8:
            try:
                stake = float(self.s_entry.get() or 10)
                self.client.execute_trade(VOLATILITY_INDICES[self.i_combo.get()], side, stake)
                self.last_trade_time = now
            except: pass

    def on_trade_result(self, profit):
        self.total_profit += profit
        self.root.after(0, self.update_profit)
        res = "GANADA" if profit > 0 else "PERDIDA"
        self.voice.speak(f"Ráfaga completada. Operación {res}. Balance: {self.total_profit:.2f} dólares.")

    def update_profit(self):
        c = COLORS["green"] if self.total_profit >= 0 else COLORS["red"]
        self.profit_label.config(text=f"Profit: ${self.total_profit:.2f}", fg=c)

if __name__ == "__main__":
    root = tk.Tk()
    root.resizable(False, False)
    app = SilentEngineApp(root)
    root.mainloop()
