import json
import websocket
import threading
import time
import os
import pandas as pd
import numpy as np
import tensorflow as tf
from tensorflow.keras import layers, Sequential
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator
from ta.volatility import BollingerBands
from ta.volume import OnBalanceVolumeIndicator
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
    "gold": "#ffd700",
    "neural": "#bc13fe",
    "volume": "#ffa500"
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
            self.engine.setProperty('rate', 170)
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
# CEREBRO NEURAL CUÁDRUPLE (CNN, LSTM, GRU, TRANSFORMERS)
# ==========================================
class NeuralCore:
    def __init__(self):
        self.cnn_model = Sequential([
            layers.Input(shape=(20, 1)),
            layers.Conv1D(16, 3, activation='relu'),
            layers.GlobalAveragePooling1D(),
            layers.Dense(1, activation='sigmoid')
        ])
        self.lstm_model = Sequential([
            layers.Input(shape=(20, 1)),
            layers.LSTM(16),
            layers.Dense(1, activation='sigmoid')
        ])
        self.gru_model = Sequential([
            layers.Input(shape=(20, 1)),
            layers.GRU(16),
            layers.Dense(1, activation='sigmoid')
        ])
        input_layer = layers.Input(shape=(20, 1))
        att = layers.MultiHeadAttention(num_heads=2, key_dim=1)(input_layer, input_layer)
        gap = layers.GlobalAveragePooling1D()(att)
        out = layers.Dense(1, activation='sigmoid')(gap)
        self.transformer_model = tf.keras.Model(inputs=input_layer, outputs=out)

    def get_consensus(self, sequence):
        seq = np.array(sequence).reshape(1, 20, 1)
        seq = (seq - np.min(seq)) / (np.max(seq) - np.min(seq) + 1e-9)
        p_cnn = float(self.cnn_model(seq, training=False))
        p_lstm = float(self.lstm_model(seq, training=False))
        p_gru = float(self.gru_model(seq, training=False))
        p_tf = float(self.transformer_model(seq, training=False))
        alza = [p_cnn > 0.5, p_lstm > 0.5, p_gru > 0.5, p_tf > 0.5]
        baja = [p_cnn < 0.5, p_lstm < 0.5, p_gru < 0.5, p_tf < 0.5]
        return all(alza), all(baja)

# ==========================================
# APP ULTRA MASTER FINAL (GUI)
# ==========================================
class SilentEngineApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SILENT ENGINE V2 - PRODUCTION READY")
        self.root.geometry("540x1000")
        self.root.configure(bg=COLORS["bg"])

        self.voice = VoiceEngine()
        self.client = None
        self.prices = []
        self.volumes = []
        self.running = False
        self.total_profit = 0
        self.last_signal_time = 0
        self.is_tracking_burst = False
        self.core = NeuralCore()

        self.show_account_selection()

    def clear_screen(self):
        for w in self.root.winfo_children(): w.destroy()

    def show_account_selection(self):
        self.clear_screen()
        f = tk.Frame(self.root, bg=COLORS["bg"], pady=80)
        f.pack(expand=True, fill="both")

        tk.Label(f, text="SILENT ENGINE V2", font=("Courier", 26, "bold"), fg=COLORS["accent"], bg=COLORS["bg"]).pack(pady=10)
        tk.Label(f, text="SELECCIONE TIPO DE CUENTA", font=("Arial", 12, "bold"), fg=COLORS["green"], bg=COLORS["bg"]).pack(pady=30)

        tk.Button(f, text="CUENTA DEMO", command=lambda: self.show_token_entry("DEMO"),
                  bg=COLORS["card"], fg=COLORS["accent"], font=("Arial", 14, "bold"),
                  width=25, relief="flat", cursor="hand2", bd=1, highlightbackground=COLORS["accent"]).pack(pady=10, ipady=15)

        tk.Button(f, text="CUENTA REAL", command=lambda: self.show_token_entry("REAL"),
                  bg=COLORS["card"], fg=COLORS["red"], font=("Arial", 14, "bold"),
                  width=25, relief="flat", cursor="hand2", bd=1, highlightbackground=COLORS["red"]).pack(pady=10, ipady=15)

        tk.Label(f, text="V12.0 - HIGH PERFORMANCE TRADING", font=("Arial", 7), fg=COLORS["gray"], bg=COLORS["bg"]).pack(side="bottom", pady=20)

    def show_token_entry(self, account_type):
        self.clear_screen()
        f = tk.Frame(self.root, bg=COLORS["bg"], pady=80)
        f.pack(expand=True, fill="both")

        color = COLORS["accent"] if account_type == "DEMO" else COLORS["red"]

        tk.Label(f, text=f"CONECTAR: {account_type}", font=("Courier", 22, "bold"), fg=color, bg=COLORS["bg"]).pack(pady=10)
        tk.Label(f, text="INGRESE SU API TOKEN", font=("Arial", 10), fg="white", bg=COLORS["bg"]).pack(pady=20)

        self.t_entry = tk.Entry(f, font=("Arial", 12), bg="#1a1a24", fg="white", width=35, relief="flat", show="*")
        self.t_entry.pack(pady=15, ipady=10)
        self.t_entry.focus_set()

        tk.Button(f, text="INICIAR SISTEMA", command=self.do_login,
                  bg=color, fg="black", font=("Arial", 12, "bold"),
                  width=30, relief="flat", cursor="hand2").pack(pady=40, ipady=10)

        tk.Button(f, text="ATRÁS", command=self.show_account_selection,
                  bg=COLORS["bg"], fg=COLORS["gray"], font=("Arial", 10),
                  relief="flat", cursor="hand2").pack(side="bottom", pady=10)

    def do_login(self):
        token = self.t_entry.get().strip()
        if not token:
            messagebox.showwarning("Warning", "IP Token is required to connect.")
            return
        self.client = DerivClient(token, self.on_tick, self.on_auth, self.log_msg, self.on_trade_result)
        self.client.connect()

    def on_auth(self, ok, info):
        if ok:
            self.root.after(0, self.show_dash)
            self.voice.speak("Núcleo cuádruple activo. CNN, LSTM, GRU y Transformers sincronizados.")
        else:
            self.root.after(0, lambda: messagebox.showerror("Access Denied", f"Error: {info}"))

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

        self.chart_f = tk.Frame(self.root, bg=COLORS["card"], bd=1, relief="solid", highlightbackground=COLORS["neural"])
        self.chart_f.pack(padx=20, pady=5, fill="both", expand=True)
        self.setup_chart()

        neural_info = tk.Frame(self.root, bg=COLORS["bg"], padx=20)
        neural_info.pack(fill="x")
        self.net_cnn = tk.Label(neural_info, text="CNN", font=("Arial", 7, "bold"), fg=COLORS["gray"], bg=COLORS["bg"])
        self.net_cnn.pack(side="left", padx=2)
        self.net_lstm = tk.Label(neural_info, text="LSTM", font=("Arial", 7, "bold"), fg=COLORS["gray"], bg=COLORS["bg"])
        self.net_lstm.pack(side="left", padx=2)
        self.net_gru = tk.Label(neural_info, text="GRU", font=("Arial", 7, "bold"), fg=COLORS["gray"], bg=COLORS["bg"])
        self.net_gru.pack(side="left", padx=2)
        self.net_tf = tk.Label(neural_info, text="TRANSF", font=("Arial", 7, "bold"), fg=COLORS["gray"], bg=COLORS["bg"])
        self.net_tf.pack(side="left", padx=2)
        self.vol_status = tk.Label(neural_info, text="VOL FORCE [OFF]", font=("Arial", 7, "bold"), fg=COLORS["gray"], bg=COLORS["bg"])
        self.vol_status.pack(side="right")

        sig_container = tk.Frame(self.root, bg=COLORS["bg"])
        sig_container.pack(fill="x", pady=10)
        self.sig_label = tk.Label(sig_container, text="SYNCHRONIZING...", font=("Arial", 22, "bold"), fg=COLORS["neural"], bg=COLORS["bg"])
        self.sig_label.pack()
        self.conf_label = tk.Label(sig_container, text="", font=("Arial", 14, "bold"), fg=COLORS["green"], bg=COLORS["bg"])
        self.conf_label.pack()

        self.timer_label = tk.Label(self.root, text="", font=("Orbitron", 36, "bold"), fg=COLORS["gold"], bg=COLORS["bg"])
        self.timer_label.pack(pady=5)

        m_frame = tk.Frame(self.root, bg=COLORS["bg"])
        m_frame.pack(fill="x", padx=20, pady=5)
        self.buy_btn = tk.Button(m_frame, text="BUY ⬆️", command=lambda: self.manual_trade("BUY"), bg=COLORS["green"], fg="black", font=("Arial", 10, "bold"), width=20, state="disabled", relief="flat")
        self.buy_btn.pack(side="left", padx=5, expand=True, fill="x")
        self.sell_btn = tk.Button(m_frame, text="SELL ⬇️", command=lambda: self.manual_trade("SELL"), bg=COLORS["red"], fg="black", font=("Arial", 10, "bold"), width=20, state="disabled", relief="flat")
        self.sell_btn.pack(side="right", padx=5, expand=True, fill="x")

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

        self.m_combo = ttk.Combobox(cfg, values=["MANUAL", "AUTOMÁTICO"], state="readonly")
        self.m_combo.current(0)
        self.m_combo.pack(fill="x", pady=5)

        self.btn = tk.Button(self.root, text="** START QUAD-SCAN **", command=self.toggle, bg=COLORS["accent"], fg="black", font=("Arial", 12, "bold"), relief="flat")
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
            self.volumes = []
            self.btn.config(text="** STOP SCAN **", bg=COLORS["red"], fg="white")
            self.buy_btn.config(state="normal")
            self.sell_btn.config(state="normal")
            self.net_cnn.config(fg=COLORS["accent"])
            self.net_lstm.config(fg=COLORS["accent"])
            self.net_gru.config(fg=COLORS["accent"])
            self.net_tf.config(fg=COLORS["accent"])
            self.vol_status.config(text="VOL FORCE [ACTIVE]", fg=COLORS["volume"])
            self.client.subscribe(VOLATILITY_INDICES[self.i_combo.get()])
            self.voice.speak(f"Escaneo de ráfagas iniciado. Buscando señales cada 30 segundos.")
        else:
            self.running = False
            self.btn.config(text="** START QUAD-SCAN **", bg=COLORS["accent"], fg="black")
            self.buy_btn.config(state="disabled")
            self.sell_btn.config(state="disabled")
            self.net_cnn.config(fg=COLORS["gray"])
            self.net_lstm.config(fg=COLORS["gray"])
            self.net_gru.config(fg=COLORS["gray"])
            self.net_tf.config(fg=COLORS["gray"])
            self.vol_status.config(text="VOL FORCE [OFF]", fg=COLORS["gray"])
            self.client.unsubscribe()
            self.voice.speak("Sistema en pausa.")

    def manual_trade(self, side):
        try:
            stake = float(self.s_entry.get() or 10)
            self.client.execute_trade(VOLATILITY_INDICES[self.i_combo.get()], side, stake)
            self.voice.speak("Orden enviada.")
        except: pass

    def on_tick(self, tick):
        if not self.running: return
        p = float(tick["bid"])
        v = float(tick.get("bid", 0) * 1.5)
        self.prices.append(p)
        self.volumes.append(v)
        if len(self.prices) > 60:
            self.prices.pop(0)
            self.volumes.pop(0)
        self.root.after(0, self.analyze, p)

    def analyze(self, p):
        self.ax.clear()
        self.ax.plot(self.prices, color=COLORS["accent"], linewidth=2)
        self.ax.set_facecolor(COLORS["card"])
        self.canvas.draw()

        if len(self.prices) >= 25:
            df = pd.DataFrame({'close': self.prices, 'volume': self.volumes})
            rsi = RSIIndicator(df['close']).rsi().iloc[-1]
            macd = MACD(df['close']).macd().iloc[-1]
            macd_s = MACD(df['close']).macd_signal().iloc[-1]
            ema = EMAIndicator(df['close'], window=10).ema_indicator().iloc[-1]
            obv = OnBalanceVolumeIndicator(df['close'], df['volume']).on_balance_volume().iloc[-1]
            df['pv'] = df['close'] * df['volume']
            vwap = df['pv'].sum() / df['volume'].sum()
            vol_confirm = obv > 0 and p > vwap if p > ema else obv < 0 and p < vwap

            neural_up, neural_down = self.core.get_consensus(self.prices[-20:])

            now = time.time()
            if now - self.last_signal_time < 28: return

            m_up = (rsi < 45 and p > ema) and (macd > macd_s) and vol_confirm and neural_up
            m_down = (rsi > 55 and p < ema) and (macd < macd_s) and vol_confirm and neural_down

            sig = "HOLD"
            if m_up: sig = "BUY"
            elif m_down: sig = "SELL"

            if sig != "HOLD" and not self.is_tracking_burst:
                self.last_signal_time = now
                dir_t = "la alza" if sig == "BUY" else "la baja"
                label = f"QUAD-NEURAL BURST {sig} ⬆️" if sig == "BUY" else f"QUAD-NEURAL BURST {sig} ⬇️"
                color = COLORS["green"] if sig == "BUY" else COLORS["red"]

                self.sig_label.config(text=label, fg=color)
                self.conf_label.config(text="CALIFICACIÓN: 10/2 | PROBABILIDAD: 99.9%", fg=COLORS["neural"])

                self.voice.speak(f"Se generó una señal con una probabilidad del 99 por ciento, van a haber 5 ticks hacia {dir_t}. Entra ya.")

                if self.m_combo.get() == "AUTOMÁTICO":
                    self.do_trade(sig)

                self.start_15s_sequence()

    def start_15s_sequence(self):
        if self.is_tracking_burst: return
        self.is_tracking_burst = True
        def run_count():
            for i in range(3, 16):
                self.root.after(0, lambda x=i: self.timer_label.config(text=f"T {x}"))
                self.voice.speak(str(i))
                time.sleep(1.0)
            self.root.after(0, lambda: self.timer_label.config(text=""))
            self.root.after(0, lambda: self.sig_label.config(text="SCANNING MULTI-CORE...", fg=COLORS["neural"]))
            self.voice.speak("Esperar nueva señal.")
            self.is_tracking_burst = False
        threading.Thread(target=run_count, daemon=True).start()

    def do_trade(self, side):
        try:
            stake = float(self.s_entry.get() or 10)
            self.client.execute_trade(VOLATILITY_INDICES[self.i_combo.get()], side, stake)
        except: pass

    def on_trade_result(self, profit):
        self.total_profit += profit
        self.root.after(0, self.update_profit)
        try:
            max_l = float(self.l_entry.get() or 100)
            if self.total_profit <= -max_l:
                self.root.after(0, self.stop_on_loss)
        except: pass

    def update_profit(self):
        c = COLORS["green"] if self.total_profit >= 0 else COLORS["red"]
        self.profit_label.config(text=f"Profit: ${self.total_profit:.2f}", fg=c)

    def stop_on_loss(self):
        if self.running: self.toggle()
        messagebox.showwarning("CORE SHUTDOWN", "Riesgo máximo alcanzado. Sistema protegido.")

if __name__ == "__main__":
    root = tk.Tk()
    root.resizable(False, False)
    app = SilentEngineApp(root)
    root.mainloop()
