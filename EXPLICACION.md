# Guía de Funcionamiento Detallada: Silent Engine V2 🚀🧠

Este documento explica el ciclo de vida completo de la aplicación, desde su ejecución hasta el cierre de una operación exitosa.

---

## 1. Inicio y Acceso Seguro 🔐
Nada más ejecutar el archivo (usando `pythonw bot.py` o haciendo doble clic en `bot.pyw` para evitar la consola negra), se despliega la interfaz gráfica:

1.  **Selección de Cuenta:** La app presenta dos botones: **Cuenta Demo** y **Cuenta Real**. Esto configura internamente el entorno de trading.
2.  **Ingreso de Token:** Al elegir una opción, se solicita el **API Token** de Deriv.
    *   *Seguridad:* El token no se guarda en el código, protegiendo tu capital.
3.  **Conexión WebSocket:** Al pulsar "Iniciar Sistema", el bot abre un túnel de datos en tiempo real con los servidores de Deriv mediante el protocolo WebSocket.

---

## 2. El Cerebro de IA: Cuádruple Consenso Neural 🤖️
Una vez dentro del panel, al pulsar **"START QUAD-SCAN"**, el motor de Inteligencia Artificial comienza a trabajar. No usa una sola red, sino **cuatro arquitecturas diferentes simultáneamente** para garantizar la máxima precisión:

1.  **CNN (Red Neuronal Convolucional):** Analiza patrones visuales en la curva de precios (picos, valles, tendencias).
2.  **LSTM (Long Short-Term Memory):** Especializada en series temporales; "recuerda" lo que pasó hace 20 ticks para predecir el siguiente movimiento.
3.  **GRU (Gated Recurrent Unit):** Similar a LSTM pero más eficiente, detecta cambios rápidos en la volatilidad.
4.  **Transformers:** La tecnología más avanzada (usada en ChatGPT), analiza la relación entre todos los puntos de la secuencia de precio actual para encontrar dependencias complejas.

**¿Cómo decide?**
Para que el bot diga "COMPRA" o "VENTA", **las 4 redes deben estar de acuerdo**. Si 3 dicen subir pero 1 dice bajar, el bot se mantiene en "HOLD" (espera). Esto filtra señales falsas.

---

## 3. Filtros Técnicos y de Volumen 📊
Además de la IA, el sistema aplica filtros de análisis técnico profesional:
*   **RSI (Fuerza Relativa):** Evita comprar cuando el mercado está demasiado caro (sobrecompra) o vender cuando está muy barato.
*   **MACD:** Confirma que el impulso del precio tiene fuerza.
*   **EMA (Media Móvil):** Asegura que operamos a favor de la tendencia principal.
*   **OBV y VWAP (Volumen):** El bot analiza el "dinero real" que entra al mercado. Si el precio sube pero el volumen baja, la IA ignora la señal porque es un movimiento débil.

---

## 4. Ejecución de la Operación y Secuencia de "Ráfaga" ⚡
Cuando hay consenso total, ocurre lo siguiente:

1.  **Anuncio de Voz:** El bot utiliza `pyttsx3` para decirte: *"Se generó una señal con una probabilidad del 99 por ciento... ¡ENTRA YA!"*.
2.  **Entrada Automática:** Si está en modo "AUTOMÁTICO", el bot lanza la orden a Deriv exactamente en el **segundo 2** de la ráfaga detectada para aprovechar el impulso máximo de 5 ticks.
3.  **Conteo de Seguimiento (Burst Tracking):**
    *   Verás un cronómetro gigante en pantalla.
    *   La voz empezará a contar desde el **segundo 3 hasta el 15**. Este es el tiempo estimado en que la ráfaga de 5 ticks se desarrolla y se estabiliza.
4.  **Cierre y Resultado:** Al finalizar el contrato (5 ticks), el bot recibe el resultado de la cuenta. Si es positivo, actualiza el "Profit" en verde. Si es negativo, lo pone en rojo.
5.  **Enfriamiento (Cooldown):** El bot espera unos 25-30 segundos antes de buscar la siguiente ráfaga para no saturar la cuenta y evitar ruidos de mercado.

---

## 5. Gestión de Riesgo (Protección de Capital) 🛡️
Durante todo el tiempo, el bot vigila el **Stop Loss**:
*   Si tus pérdidas acumuladas alcanzan el límite que configuraste en la interfaz, el bot **apaga el motor automáticamente** y desconecta el escaneo.
*   Esto evita que una mala racha agote tu saldo.

---

**Resumen:** El bot combina **Matemáticas Avanzadas (IA)**, **Psicología de Mercado (Volumen)** y **Velocidad de Reacción (Automatización)** para operar ráfagas cortas y precisas.
