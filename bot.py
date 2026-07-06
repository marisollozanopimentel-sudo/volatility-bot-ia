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
import sys

# Cargar variables de entorno
load_dotenv()

# Configuración de logs
if not os.path.exists("logs"):
    os.makedirs("logs")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/trading.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Parámetros Globales
DERIV_TOKEN = os.getenv("DERIV_TOKEN", "")
DERIV_API_URL = "wss://ws.deriv.com/websockets/v3"
SCAN_INTERVAL = 10
MIN_CONFIDENCE = 95
DEFAULT_STAKE = 10
MAX_LOSS = 100

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
    def __init__(self, language="es"):
        try:
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', 150)
            self.engine.setProperty('volume', 0.9)
        except Exception as e:
            logger.warning(f"No se pudo inicializar el motor de voz: {e}")
            self.engine = None

        self.language = language
        self.queue = Queue()
        self.thread = threading.Thread(target=self._speak_worker, daemon=True)
        self.thread.start()

    def _speak_worker(self):
        while True:
            text = self.queue.get()
            if text and self.engine:
                try:
                    self.engine.say(text)
                    self.engine.runAndWait()
                except Exception as e:
                    logger.error(f"Error en el motor de voz: {e}")

    def speak(self, text):
        if self.engine:
            self.queue.put(text)
        else:
            logger.info(f"VOZ (desactivada): {text}")

    def speak_signal(self, signal, confidence, price):
        if signal == "BUY":
            text = f"Señal de compra confirmada con {confidence:.0f} por ciento de confianza. Precio actual {price:.2f}. Ejecutando operación."
        elif signal == "SELL":
            text = f"Señal de venta confirmada con {confidence:.0f} por ciento de confianza. Precio actual {price:.2f}. Ejecutando operación."
        else:
            text = f"Sin señal clara. Confianza {confidence:.0f} por ciento."
        self.speak(text)

    def speak_welcome(self):
        self.speak("Bienvenido al Bot de Trading con Inteligencia Artificial. Sistema iniciado.")

    def speak_connected(self):
        self.speak("Conexión a Derivados establecida exitosamente.")

    def speak_starting_analysis(self, symbol):
        self.speak(f"Iniciando análisis en tiempo real del índice {symbol}. Sistema escaneará el mercado cada diez segundos.")

    def speak_trade_executed(self, stake, account):
        text = f"Operación ejecutada. Inversión de {stake} dólares en cuenta {account}."
        self.speak(text)

    def speak_error(self, error_msg):
        self.speak(f"Error. {error_msg}")

class DerivClient:
    def __init__(self, token, account_type="demo", voice_engine=None):
        self.token = token
        self.account_type = account_type
        self.ws = None
        self.connected = False
        self.market_data = {}
        self.callbacks = []
        self.authorize_response = None
        self.voice = voice_engine

    def connect(self):
        try:
            self.ws = websocket.WebSocketApp(
                DERIV_API_URL,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                on_open=self._on_open
            )

            self.ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
            self.ws_thread.start()

            logger.info("Conectando a Deriv...")

            # Esperar a que se conecte y autorice
            timeout = 10
            start_time = time.time()
            while not self.connected and time.time() - start_time < timeout:
                time.sleep(0.5)

            return self.connected

        except Exception as e:
            logger.error(f"Error conectando a Deriv: {e}")
            if self.voice:
                self.voice.speak_error(f"No se pudo conectar a Derivados. {str(e)}")
            return False

    def _on_open(self, ws):
        logger.info("Conexión abierta a Deriv")

        auth_msg = {
            "authorize": self.token,
            "add_to_login_history": 1
        }
        self.ws.send(json.dumps(auth_msg))
        logger.info("Token enviado para autorización")

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)

            if "authorize" in data:
                self.authorize_response = data
                if "error" in data:
                    error = data.get("error", {}).get("message", "Unknown error")
                    logger.error(f"❌ Error de autorización: {error}")
                    self.connected = False
                    if self.voice:
                        self.voice.speak_error(f"Error de autorización. {error}")
                else:
                    email = data.get("authorize", {}).get("email", "Unknown")
                    logger.info(f"✅ Autorizado exitosamente. Email: {email}")
                    self.connected = True
                    if self.voice:
                        self.voice.speak_connected()

            if "tick" in data:
                symbol = data["tick"].get("symbol")
                bid = data["tick"].get("bid")
                ask = data["tick"].get("ask")
                self.market_data[symbol] = {
                    "bid": bid,
                    "ask": ask,
                    "time": data["tick"].get("time")
                }

                for callback in self.callbacks:
                    callback("tick", data["tick"])

            if "buy" in data:
                if "error" in data:
                    logger.error(f"❌ Error en compra: {data['error']['message']}")
                else:
                    logger.info(f"✅ Operación exitosa: {data['buy']['contract_id']}")

        except Exception as e:
            logger.error(f"Error procesando mensaje: {e}")

    def _on_error(self, ws, error):
        logger.error(f"❌ Error WebSocket: {error}")
        self.connected = False

    def _on_close(self, ws, close_status_code, close_msg):
        logger.warning(f"⚠️ Conexión cerrada: {close_msg}")
        self.connected = False

    def subscribe_ticks(self, symbol):
        if not self.ws or not self.connected:
            logger.error("No hay conexión. Conecta primero.")
            return

        msg = {
            "ticks": symbol,
            "subscribe": 1
        }
        self.ws.send(json.dumps(msg))
        logger.info(f"📊 Suscrito a: {symbol}")

    def unsubscribe_ticks(self, symbol):
        if not self.ws:
            return

        msg = {
            "ticks": symbol,
            "subscribe": 0
        }
        try:
            self.ws.send(json.dumps(msg))
            logger.info(f"Desuscrito de: {symbol}")
        except:
            pass

    def execute_trade(self, symbol, contract_type, stake):
        if not self.connected:
            logger.error("No se puede ejecutar operación: Sin conexión")
            return

        # Para opciones Rise/Fall en Deriv
        # CALL para compra (sube), PUT para venta (baja)
        deriv_contract_type = "CALL" if contract_type == "BUY" else "PUT"

        msg = {
            "buy": "1",
            "price": stake,
            "parameters": {
                "amount": stake,
                "basis": "stake",
                "contract_type": deriv_contract_type,
                "currency": "USD",
                "duration": 5,
                "duration_unit": "t",
                "symbol": symbol
            }
        }

        logger.info(f"🚀 Enviando orden: {contract_type} en {symbol} con {stake} USD")
        self.ws.send(json.dumps(msg))

    def get_market_data(self, symbol):
        return self.market_data.get(symbol, None)

    def add_callback(self, callback):
        self.callbacks.append(callback)

    def disconnect(self):
        if self.ws:
            self.ws.close()
            logger.info("Desconectado de Deriv")
            self.connected = False

class TechnicalIndicators:
    def __init__(self):
        self.prices = []

    def add_price(self, price):
        self.prices.append(price)
        if len(self.prices) > 500:
            self.prices.pop(0)

    def calculate_all(self):
        if len(self.prices) < 30: # Aumentado para asegurar que los indicadores tengan suficientes datos
            return {}

        try:
            df = pd.DataFrame({'close': self.prices})
            results = {}

            # RSI
            rsi = RSIIndicator(close=df['close'], window=14)
            results['rsi'] = float(rsi.rsi().iloc[-1])

            # MACD
            macd = MACD(close=df['close'], window_fast=12, window_slow=26, window_sign=9)
            results['macd'] = float(macd.macd().iloc[-1])
            results['macd_signal'] = float(macd.macd_signal().iloc[-1])

            # SMA & EMA
            sma = SMAIndicator(close=df['close'], window=20)
            results['sma'] = float(sma.sma_indicator().iloc[-1])

            ema = EMAIndicator(close=df['close'], window=12)
            results['ema'] = float(ema.ema_indicator().iloc[-1])

            # Bollinger Bands
            bb = BollingerBands(close=df['close'], window=20, window_dev=2)
            results['bb_high'] = float(bb.bollinger_hband().iloc[-1])
            results['bb_mid'] = float(bb.bollinger_mavg().iloc[-1])
            results['bb_low'] = float(bb.bollinger_lband().iloc[-1])

            results['current_price'] = self.prices[-1]
            return results

        except Exception as e:
            logger.error(f"Error calculando indicadores: {e}")
            return {}

class TradingAI:
    def __init__(self, voice_engine=None):
        self.model_ready = True
        self.voice = voice_engine

    def predict_signal(self, indicators_data):
        try:
            buy_score = 0
            sell_score = 0

            current_price = indicators_data.get('current_price', 0)
            rsi = indicators_data.get('rsi', 50)

            # Lógica RSI
            if rsi < 30:
                buy_score += 25
            elif rsi > 70:
                sell_score += 25

            # Lógica MACD
            macd = indicators_data.get('macd', 0)
            macd_signal = indicators_data.get('macd_signal', 0)
            if macd > macd_signal:
                buy_score += 20
            elif macd < macd_signal:
                sell_score += 20

            # Lógica SMA/EMA
            sma = indicators_data.get('sma', current_price)
            if current_price > sma:
                buy_score += 15
            else:
                sell_score += 15

            ema = indicators_data.get('ema', current_price)
            if current_price > ema:
                buy_score += 15
            else:
                sell_score += 15

            # Lógica Bollinger
            bb_high = indicators_data.get('bb_high', current_price)
            bb_low = indicators_data.get('bb_low', current_price)
            if current_price < bb_low:
                buy_score += 25
            elif current_price > bb_high:
                sell_score += 25

            total_score = buy_score + sell_score
            if total_score == 0: return 'HOLD', 50

            if buy_score > sell_score:
                signal = 'BUY'
                confidence = (buy_score / (buy_score + sell_score)) * 100
            elif sell_score > buy_score:
                signal = 'SELL'
                confidence = (sell_score / (buy_score + sell_score)) * 100
            else:
                signal = 'HOLD'
                confidence = 50

            return signal, confidence

        except Exception as e:
            logger.error(f"Error en predicción: {e}")
            return 'HOLD', 0

class TradingBot:
    def __init__(self):
        self.voice = VoiceEngine(language="es")
        self.client = DerivClient(DERIV_TOKEN, "demo", voice_engine=self.voice)
        self.ai = TradingAI(voice_engine=self.voice)
        self.indicators = TechnicalIndicators()
        self.running = False
        self.current_symbol = None
        self.mode = "manual"
        self.stake = DEFAULT_STAKE
        self.max_loss = MAX_LOSS
        self.account_type = "demo"

    def start(self):
        print("\n" + "="*60)
        print("🤖 VOLATILITY BOT IA - INICIANDO")
        print("="*60)

        if not DERIV_TOKEN:
            logger.error("❌ No se encontró DERIV_TOKEN en el archivo .env")
            return False

        self.voice.speak_welcome()

        if not self.client.connect():
            logger.error("❌ No se pudo conectar a Deriv")
            return False

        self.client.add_callback(self._on_market_data)
        self.running = True
        return True

    def _on_market_data(self, data_type, data):
        if data_type == "tick":
            price = data.get("bid", 0)
            if price:
                self.indicators.add_price(price)

    def select_symbol(self):
        print("\n" + "="*60)
        print("📊 ÍNDICES DISPONIBLES")
        print("="*60)
        for i, (name, symbol) in enumerate(VOLATILITY_INDICES.items(), 1):
            print(f"{i}. {name}")

        while True:
            try:
                choice = int(input("\nSelecciona un número: "))
                if 1 <= choice <= len(VOLATILITY_INDICES):
                    self.current_symbol = list(VOLATILITY_INDICES.values())[choice - 1]
                    symbol_name = list(VOLATILITY_INDICES.keys())[choice - 1]
                    logger.info(f"✅ Símbolo seleccionado: {symbol_name} ({self.current_symbol})")
                    self.voice.speak(f"Índice seleccionado. {symbol_name}")
                    break
                else:
                    print("❌ Número inválido")
            except ValueError:
                print("❌ Ingresa un número válido")

    def select_account_type(self):
        print("\n" + "="*60)
        print("💰 TIPO DE CUENTA")
        print("="*60)
        print("1. Demo")
        print("2. Real")

        choice = input("\nSelecciona (1 o 2): ")
        if choice == "2":
            confirm = input("⚠️ ¿Confirmas operar con dinero REAL? (s/n): ")
            if confirm.lower() == "s":
                self.account_type = "real"
                self.voice.speak("Atención. Modo cuenta real activado.")
            else:
                self.account_type = "demo"
        else:
            self.account_type = "demo"
            self.voice.speak("Modo demostración seleccionado")

    def select_mode(self):
        print("\n" + "="*60)
        print("⚙️ MODO DE OPERACIÓN")
        print("="*60)
        print("1. AUTOMÁTICO")
        print("2. MANUAL")

        choice = input("\nSelecciona (1 o 2): ")
        if choice == "1":
            self.mode = "automático"
            self.voice.speak("Modo automático activado.")
            self.configure_auto_settings()
        else:
            self.mode = "manual"
            self.voice.speak("Modo manual seleccionado.")

    def configure_auto_settings(self):
        try:
            val = input(f"Stake por operación (USD) [{DEFAULT_STAKE}]: ")
            self.stake = float(val) if val else DEFAULT_STAKE
            val = input(f"Pérdida máxima (USD) [{MAX_LOSS}]: ")
            self.max_loss = float(val) if val else MAX_LOSS
        except ValueError:
            logger.warning("Entrada inválida, usando valores por defecto")

    def run_analysis_loop(self):
        print("\n" + "="*60)
        print(f"🚀 INICIANDO ANÁLISIS - {self.current_symbol}")
        print(f"📈 Modo: {self.mode.upper()} | Cuenta: {self.account_type.upper()}")
        print("Presiona Ctrl+C para detener")
        print("="*60 + "\n")

        self.voice.speak_starting_analysis(self.current_symbol)
        self.client.subscribe_ticks(self.current_symbol)

        try:
            while self.running:
                indicators = self.indicators.calculate_all()
                if indicators:
                    signal, confidence = self.ai.predict_signal(indicators)

                    print(f"⏰ {time.strftime('%H:%M:%S')} | Precio: {indicators['current_price']:.2f} | RSI: {indicators['rsi']:.1f} | Señal: {signal} ({confidence:.1f}%)", end='\r')

                    if confidence >= MIN_CONFIDENCE and signal != 'HOLD':
                        print(f"\n\n🔥 SEÑAL DETECTADA: {signal} con {confidence:.1f}% de confianza")
                        self.voice.speak_signal(signal, confidence, indicators['current_price'])

                        if self.mode == "automático":
                            self._execute_trade(signal, confidence)
                        else:
                            self._manual_confirmation(signal, confidence)
                else:
                    print(f"⏳ Obteniendo datos de mercado... ({len(self.indicators.prices)}/30)", end='\r')

                time.sleep(SCAN_INTERVAL)
        except KeyboardInterrupt:
            logger.info("Bot detenido por el usuario")
        finally:
            self.stop()

    def _execute_trade(self, signal, confidence):
        logger.info(f"Ejecutando operación automática: {signal}")
        self.client.execute_trade(self.current_symbol, signal, self.stake)
        self.voice.speak_trade_executed(self.stake, self.account_type)

    def _manual_confirmation(self, signal, confidence):
        print(f"\n❓ ¿Deseas ejecutar {signal}? (s/n): ", end='')
        # Nota: input() bloquea el loop. En una app real usaríamos algo no bloqueante.
        confirm = input().lower()
        if confirm == 's':
            self._execute_trade(signal, confidence)
        else:
            print("Operación cancelada.")

    def stop(self):
        self.running = False
        if self.current_symbol:
            self.client.unsubscribe_ticks(self.current_symbol)
        self.client.disconnect()
        logger.info("Bot finalizado correctamente")

if __name__ == "__main__":
    bot = TradingBot()
    if bot.start():
        bot.select_symbol()
        bot.select_account_type()
        bot.select_mode()
        bot.run_analysis_loop()
