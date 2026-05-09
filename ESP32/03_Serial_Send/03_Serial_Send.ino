/*
  bici-interactiva - Lector de velocidad para ESP32 DevKit V1

  Sensor:
  - 49E / SS49E / 49E 945BC
  - Salida analógica proporcional al campo magnético

  Conexión sensor:
  - VCC  -> 3.3V
  - GND  -> GND
  - OUT  -> GPIO4

  Conexión botón:
  - Una pata -> GPIO23 / D23
  - Otra pata -> GND

  Conexión UART hacia Raspberry Pi:
  - ESP32 GPIO17 TX2 -> Raspberry GPIO15 RXD / pin físico 10
  - ESP32 GPIO16 RX2 <- Raspberry GPIO14 TXD / pin físico 8
  - ESP32 GND       -> Raspberry GND

  Salida durante prueba activa:
  START
  speed_kmh,speed_smooth_kmh
  0.000,0.000
  ...
  END

  Serial:
  - Serial por USB para depuración
  - Serial2 por pines TX/RX hacia Raspberry Pi
*/

#include <Arduino.h>

// =====================================================
// CONFIGURACIÓN GENERAL
// =====================================================

// Pin ADC del ESP32 para el sensor Hall
const int HALL_PIN = 4;

// Pin del botón de inicio
const int START_BUTTON_PIN = 23;

// Duración de la prueba
const uint32_t TEST_DURATION_MS = 60000;

// Número de imanes en la rueda
const uint8_t NUM_MAGNETS = 9;

// Diámetro de la rueda en pulgadas
const float WHEEL_DIAMETER_INCH = 27.0;

// Distancia del imán al centro, en pulgadas.
// No se usa para velocidad de avance.
// Solo queda documentada.
const float MAGNET_RADIUS_INCH = 11.0;

// Frecuencia de reporte
// 10 Hz = 10 muestras por segundo
const uint16_t REPORT_HZ = 10;

// Baud rate USB y UART
const uint32_t SERIAL_BAUD = 19200;

// UART físico hacia Raspberry Pi
const int ESP32_RX2_PIN = 16;
const int ESP32_TX2_PIN = 17;

// =====================================================
// CONFIGURACIÓN DEL SENSOR
// =====================================================

const bool USE_ABSOLUTE_FIELD = true;

// Umbral para detectar que pasó un imán
const int THRESHOLD_ON = 250;

// Umbral para liberar detección
const int THRESHOLD_OFF = 120;

// Tiempo mínimo entre pulsos para evitar doble detección
const uint32_t MIN_PULSE_INTERVAL_US = 10000;

// Si no hay pulsos durante este tiempo, velocidad = 0
const uint32_t SPEED_TIMEOUT_MS = 1500;

// Cantidad de lecturas para calibrar baseline
const uint16_t CALIBRATION_SAMPLES = 500;

// Intervalo entre reportes
const uint32_t REPORT_INTERVAL_MS = 1000UL / REPORT_HZ;

// =====================================================
// CONFIGURACIÓN DEL BOTÓN
// =====================================================

// Antirrebote del botón
const uint32_t BUTTON_DEBOUNCE_MS = 50;

bool lastButtonReading = HIGH;
bool stableButtonState = HIGH;
uint32_t lastButtonChangeMs = 0;

// =====================================================
// CÁLCULOS FÍSICOS
// =====================================================

const float INCH_TO_M = 0.0254;
const float WHEEL_DIAMETER_M = WHEEL_DIAMETER_INCH * INCH_TO_M;
const float WHEEL_CIRCUMFERENCE_M = PI * WHEEL_DIAMETER_M;

// =====================================================
// VARIABLES DE ESTADO
// =====================================================

int baseline = 2048;
int rawValue = 0;
int fieldValue = 0;

bool magnetActive = false;

uint32_t lastPulseUs = 0;
uint32_t currentPulseUs = 0;
uint32_t pulseIntervalUs = 0;

uint32_t lastReportMs = 0;
uint32_t lastPulseMs = 0;

uint32_t pulseCount = 0;

float rpm = 0.0;
float speedKmh = 0.0;
float speedSmoothKmh = 0.0;

// Factor de suavizado
const float SMOOTH_ALPHA = 0.25;

// Estado de la prueba
bool testActive = false;
uint32_t testStartMs = 0;

// =====================================================
// FUNCIONES DE SALIDA DOBLE: USB + UART RASPBERRY
// =====================================================

void sendLine(const String &line) {
  Serial.println(line);
  Serial2.println(line);
}

void sendCsvHeader() {
  sendLine("speed_kmh,speed_smooth_kmh");
}

void sendDataLine(float speed, float smooth) {
  // USB
  Serial.print(speed, 3);
  Serial.print(",");
  Serial.println(smooth, 3);

  // UART hacia Raspberry Pi
  Serial2.print(speed, 3);
  Serial2.print(",");
  Serial2.println(smooth, 3);
}

void sendComment(const String &line) {
  // Los comentarios solo son útiles en USB.
  // No los mandamos a Raspberry para mantener limpio el parser.
  Serial.println(line);
}

// =====================================================
// FUNCIONES DE SENSOR
// =====================================================

int readHallAveraged(uint8_t samples = 4) {
  long sum = 0;

  for (uint8_t i = 0; i < samples; i++) {
    sum += analogRead(HALL_PIN);
  }

  return sum / samples;
}

void calibrateBaseline() {
  long sum = 0;

  sendComment("# Calibrando sensor Hall...");
  sendComment("# No muevas la rueda durante la calibracion.");

  for (uint16_t i = 0; i < CALIBRATION_SAMPLES; i++) {
    sum += analogRead(HALL_PIN);
    delay(2);
  }

  baseline = sum / CALIBRATION_SAMPLES;

  Serial.print("# Baseline ADC: ");
  Serial.println(baseline);
}

void resetSpeedState() {
  rawValue = 0;
  fieldValue = 0;

  magnetActive = false;

  lastPulseUs = 0;
  currentPulseUs = 0;
  pulseIntervalUs = 0;

  lastPulseMs = 0;
  lastReportMs = millis();

  pulseCount = 0;

  rpm = 0.0;
  speedKmh = 0.0;
  speedSmoothKmh = 0.0;
}

void updateSpeedFromPulse(uint32_t nowUs) {
  currentPulseUs = nowUs;

  if (lastPulseUs > 0) {
    pulseIntervalUs = currentPulseUs - lastPulseUs;

    float pulseIntervalSec = pulseIntervalUs / 1000000.0;

    if (pulseIntervalSec > 0.0) {
      float pulsesPerSecond = 1.0 / pulseIntervalSec;
      float revolutionsPerSecond = pulsesPerSecond / NUM_MAGNETS;

      rpm = revolutionsPerSecond * 60.0;

      float speedMs = revolutionsPerSecond * WHEEL_CIRCUMFERENCE_M;
      speedKmh = speedMs * 3.6;

      speedSmoothKmh =
        (SMOOTH_ALPHA * speedKmh) +
        ((1.0 - SMOOTH_ALPHA) * speedSmoothKmh);
    }
  }

  lastPulseUs = currentPulseUs;
  lastPulseMs = millis();
  pulseCount++;
}

void detectMagnetPulse() {
  rawValue = readHallAveraged(4);

  int delta = rawValue - baseline;

  if (USE_ABSOLUTE_FIELD) {
    fieldValue = abs(delta);
  } else {
    fieldValue = delta;
  }

  uint32_t nowUs = micros();

  if (!magnetActive && fieldValue >= THRESHOLD_ON) {
    if (lastPulseUs == 0 || (nowUs - lastPulseUs) >= MIN_PULSE_INTERVAL_US) {
      magnetActive = true;
      updateSpeedFromPulse(nowUs);
    }
  }

  if (magnetActive && fieldValue <= THRESHOLD_OFF) {
    magnetActive = false;
  }
}

void updateTimeout() {
  uint32_t nowMs = millis();

  if (lastPulseMs > 0 && (nowMs - lastPulseMs) > SPEED_TIMEOUT_MS) {
    speedKmh = 0.0;
    speedSmoothKmh = 0.0;
    rpm = 0.0;
  }
}

// =====================================================
// FUNCIONES DE BOTÓN Y PRUEBA
// =====================================================

bool startButtonPressedEvent() {
  bool reading = digitalRead(START_BUTTON_PIN);
  uint32_t nowMs = millis();

  if (reading != lastButtonReading) {
    lastButtonChangeMs = nowMs;
    lastButtonReading = reading;
  }

  if ((nowMs - lastButtonChangeMs) > BUTTON_DEBOUNCE_MS) {
    if (reading != stableButtonState) {
      stableButtonState = reading;

      // Evento de presión: pasa de HIGH a LOW
      if (stableButtonState == LOW) {
        return true;
      }
    }
  }

  return false;
}

void startTest() {
  testActive = true;
  testStartMs = millis();

  resetSpeedState();

  sendLine("START");
  sendCsvHeader();
}

void stopTest() {
  testActive = false;

  speedKmh = 0.0;
  speedSmoothKmh = 0.0;
  rpm = 0.0;

  sendLine("END");
}

void updateTestState() {
  uint32_t nowMs = millis();

  if (!testActive) {
    if (startButtonPressedEvent()) {
      startTest();
    }
    return;
  }

  if ((nowMs - testStartMs) >= TEST_DURATION_MS) {
    stopTest();
  }
}

// =====================================================
// SALIDA SERIAL
// =====================================================

void printSerialReport() {
  if (!testActive) {
    return;
  }

  uint32_t nowMs = millis();

  if (nowMs - lastReportMs >= REPORT_INTERVAL_MS) {
    lastReportMs = nowMs;

    sendDataLine(speedKmh, speedSmoothKmh);
  }
}

// =====================================================
// SETUP
// =====================================================

void setup() {
  // USB hacia computadora / Arduino IDE
  Serial.begin(SERIAL_BAUD);

  // UART físico hacia Raspberry Pi
  Serial2.begin(SERIAL_BAUD, SERIAL_8N1, ESP32_RX2_PIN, ESP32_TX2_PIN);

  delay(1000);

  pinMode(START_BUTTON_PIN, INPUT_PULLUP);

  analogReadResolution(12);
  analogSetPinAttenuation(HALL_PIN, ADC_11db);

  Serial.println();
  sendComment("# bici-interactiva - lector de velocidad ESP32");
  sendComment("# USB Serial activo para depuracion.");
  sendComment("# UART Serial2 activo hacia Raspberry Pi.");
  sendComment("# ESP32 TX2 GPIO17 -> Raspberry RXD GPIO15 / pin 10.");
  sendComment("# ESP32 RX2 GPIO16 <- Raspberry TXD GPIO14 / pin 8.");
  sendComment("# Esperando boton de inicio en GPIO23.");
  sendComment("# Cada prueba dura 60 segundos.");

  calibrateBaseline();

  Serial.print("# Diametro rueda pulgadas: ");
  Serial.println(WHEEL_DIAMETER_INCH);

  Serial.print("# Circunferencia rueda metros: ");
  Serial.println(WHEEL_CIRCUMFERENCE_M, 4);

  Serial.print("# Numero de imanes: ");
  Serial.println(NUM_MAGNETS);

  Serial.print("# Radio imanes pulgadas, documentado no usado para velocidad: ");
  Serial.println(MAGNET_RADIUS_INCH);

  sendComment("# READY");
}

// =====================================================
// LOOP NO BLOQUEANTE
// =====================================================

void loop() {
  updateTestState();

  if (testActive) {
    detectMagnetPulse();
    updateTimeout();
    printSerialReport();
  }
}