import json
import websocket
import threading
import time
import logging
import os
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands
import pyttsx3
from queue import Queue
import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.animation as animation

# Configuración básica
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

class VoiceEngine:
    def __init__(self):
        try:
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', 160)
        except: self.engine = None
        self.queue = Queue()
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        while True:
            t = self.queue.get()
            if t and self.engine:
                try:
                    self.engine.say(t)
                    self.engine.runAndWait()
                except: pass

    def speak(self, text):
        if self.engine: self.queue.put(text)

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
            on_message=self._message,
            on_error=lambda ws, e: self.log(f"Error: {e}"),
            on_open=self._open
        )
        threading.Thread(target=self.ws.run_forever, daemon=True).start()

    def _open(self, ws):
        ws.send(json.dumps({"authorize": self.token}))

    def _message(self, ws, msg):
        data = json.loads(msg)
        if "authorize" in data:
            if "error" in data:
                self.log("❌ Token Inválido")
                self.on_auth(False)
            else:
                self.connected = True
                self.on_auth(True)
        if "tick" in data:
            self.on_tick(data["tick"])

    def subscribe(self, symbol):
        if self.ws: self.ws.send(json.dumps({"ticks": symbol, "subscribe": 1}))

    def buy(self, symbol, side, stake):
        if not self.connected: return
        self.ws.send(json.dumps({
            "buy": "1", "price": stake,
            "parameters": {
                "amount": stake, "basis": "stake", "contract_type": "CALL" if side=="BUY" else "PUT",
                "currency": "USD", "duration": 5, "duration_unit": "t", "symbol": symbol
            }
        }))

class FuturisticBotApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SILENT ENGINE V2 - AI TRADING")
        self.root.geometry("450x800")
        self.root.configure(bg=COLORS["bg"])

        self.token = ""
        self.prices = []
        self.voice = VoiceEngine()
        self.client = None
        self.running = False
        self.last_signal = "BUSCANDO..."

        self.show_login()

    def clear_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def show_login(self):
        self.clear_screen()

        frame = tk.Frame(self.root, bg=COLORS["bg"], pady=100)
        frame.pack(expand=True, fill="both")

        tk.Label(frame, text="Enter Access Token", font=("Orbitron", 18, "bold"), fg=COLORS["accent"], bg=COLORS["bg"]).pack(pady=20)

        self.token_entry = tk.Entry(frame, font=("Arial", 12), bg="#1a1a24", fg="white", insertbackground="white", width=30, relief="flat", show="*")
        self.token_entry.pack(pady=10, ipady=8)

        login_btn = tk.Button(frame, text="LOGIN", command=self.attempt_login, bg=COLORS["accent"], fg="black", font=("Arial", 12, "bold"), width=20, relief="flat", activebackground=COLORS["green"])
        login_btn.pack(pady=30, ipady=5)

        tk.Label(frame, text="PROTECTED BY NEURAL SCAN", font=("Arial", 8), fg=COLORS["gray"], bg=COLORS["bg"]).pack(side="bottom", pady=20)

    def attempt_login(self):
        token = self.token_entry.get()
        if not token: return
        self.token = token
        self.client = DerivClient(token, self.on_tick, self.on_auth, print)
        self.client.connect()

    def on_auth(self, success):
        if success:
            self.root.after(0, self.show_main)
            self.voice.speak("Sitema autorizado. Iniciando motor neural.")
        else:
            messagebox.showerror("Error", "Token de acceso denegado.")

    def show_main(self):
        self.clear_screen()

        # Header
        header = tk.Frame(self.root, bg=COLORS["bg"], padx=20, pady=10)
        header.pack(fill="x")

        tk.Label(header, text="** SILENT ENGINE V2 **", font=("Courier", 14, "bold"), fg=COLORS["accent"], bg=COLORS["bg"]).pack()

        info_frame = tk.Frame(self.root, bg=COLORS["bg"], padx=20)
        info_frame.pack(fill="x")
        tk.Label(info_frame, text='"SIGNAL_LOCKED"', font=("Arial", 8), fg=COLORS["accent"], bg=COLORS["bg"]).pack(side="left")
        tk.Label(info_frame, text='"99.99% ACC"', font=("Arial", 8), fg=COLORS["accent"], bg=COLORS["bg"]).pack(side="right")

        # Chart Frame
        self.chart_frame = tk.Frame(self.root, bg=COLORS["card"], bd=1, relief="solid", highlightbackground=COLORS["accent"], highlightthickness=1)
        self.chart_frame.pack(padx=20, pady=10, fill="both", expand=True)

        self.setup_chart()

        # Signal Display
        self.signal_label = tk.Label(self.root, text="ANALIZANDO MERCADO...", font=("Orbitron", 16, "bold"), fg=COLORS["green"], bg=COLORS["bg"], pady=20)
        self.signal_label.pack()

        # Controls
        ctrl_frame = tk.Frame(self.root, bg=COLORS["bg"], pady=10)
        ctrl_frame.pack(fill="x", padx=20)

        self.symbol_combo = ttk.Combobox(ctrl_frame, values=list(VOLATILITY_INDICES.keys()), state="readonly")
        self.symbol_combo.current(0)
        self.symbol_combo.pack(fill="x", pady=5)

        self.start_btn = tk.Button(self.root, text="** START NEURAL SCAN **", command=self.toggle_scan, bg=COLORS["card"], fg=COLORS["accent"], font=("Arial", 10, "bold"), relief="solid", bd=1, pady=10)
        self.start_btn.pack(fill="x", padx=40, pady=10)

        tk.Label(self.root, text='"JOIN TELEGRAM CHANNEL"', font=("Arial", 8), fg=COLORS["gray"], bg=COLORS["bg"]).pack(pady=10)

    def setup_chart(self):
        self.fig, self.ax = plt.subplots(figsize=(4, 3), facecolor=COLORS["card"])
        self.ax.set_facecolor(COLORS["card"])
        self.ax.tick_params(colors=COLORS["gray"], labelsize=8)
        for spine in self.ax.spines.values(): spine.set_visible(False)
        self.ax.grid(color="#222233", linestyle='--', linewidth=0.5)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.chart_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def toggle_scan(self):
        if not self.running:
            self.running = True
            self.start_btn.config(text="** STOP SCAN **", fg=COLORS["red"])
            symbol = VOLATILITY_INDICES[self.symbol_combo.get()]
            self.client.subscribe(symbol)
            self.voice.speak(f"Iniciando escaneo neural en {self.symbol_combo.get()}")
        else:
            self.running = False
            self.start_btn.config(text="** START NEURAL SCAN **", fg=COLORS["accent"])
            self.signal_label.config(text="SISTEMA PAUSADO", fg=COLORS["gray"])

    def on_tick(self, tick):
        if not self.running: return
        price = tick["bid"]
        self.prices.append(price)
        if len(self.prices) > 50: self.prices.pop(0)

        self.root.after(0, self.update_ui, price)

    def update_ui(self, current_price):
        # Update Chart
        self.ax.clear()
        self.ax.set_facecolor(COLORS["card"])
        self.ax.grid(color="#222233", linestyle='--', linewidth=0.5)
        self.ax.plot(self.prices, color=COLORS["accent"], linewidth=1.5)
        self.canvas.draw()

        # AI Logic
        if len(self.prices) >= 20:
            df = pd.DataFrame({'close': self.prices})
            rsi = RSIIndicator(df['close'], window=14).rsi().iloc[-1]

            if rsi < 35:
                self.set_signal("STRONG CALL ⬆️", COLORS["green"])
            elif rsi > 65:
                self.set_signal("STRONG PUT ⬇️", COLORS["red"])
            else:
                self.set_signal("WAITING FOR SIGNAL...", COLORS["accent"])

    def set_signal(self, text, color):
        if self.last_signal != text:
            self.signal_label.config(text=text, fg=color)
            if "STRONG" in text:
                self.voice.speak(f"Atención. {text}")
            self.last_signal = text

if __name__ == "__main__":
    root = tk.Tk()
    # Intentar poner una fuente futurista si existe, si no usa Arial
    app = FuturisticBotApp(root)
    root.mainloop()
