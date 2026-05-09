/*
  bici-interactiva - Lector de velocidad para ESP32 DevKit V1

  Sensor:
  - 49E / SS49E / 49E 945BC
  - Salida analógica proporcional al campo magnético

  Conexión:
  - VCC  -> 3.3V
  - GND  -> GND
  - OUT  -> GPIO34

  Salida Serial CSV:
  millis,raw,baseline,field,pulse_count,rpm,speed_kmh,speed_smooth_kmh,status

  Autor: versión base para instalación interactiva de bicicleta
*/

#include <Arduino.h>

// =====================================================
// CONFIGURACIÓN GENERAL
// =====================================================

// Pin ADC del ESP32
const int HALL_PIN = 4;

// Número de imanes en la rueda
const uint8_t NUM_MAGNETS = 9;

// Diámetro de la rueda en pulgadas
const float WHEEL_DIAMETER_INCH = 27.0;

// Distancia del imán al centro, en pulgadas.
// Ojo: no se usa para calcular velocidad de avance.
// Solo se deja documentada por claridad.
const float MAGNET_RADIUS_INCH = 11.0;

// Frecuencia de reporte por Serial
// 10 Hz = 10 muestras por segundo
const uint16_t REPORT_HZ = 10;

// Baud rate.
// Para cable largo conviene no exagerar.
const uint32_t SERIAL_BAUD = 19200;

// =====================================================
// CONFIGURACIÓN DEL SENSOR
// =====================================================

// El 49E entrega ~VCC/2 sin campo.
// Con ESP32 a 12 bits: 0-4095.
// Sin campo debería rondar 2048, pero depende del sensor.

// Si todos los imanes tienen la misma polaridad orientada al sensor,
// puedes detectar solo campo positivo o negativo.
// Si no estás segura de la polaridad, usa detección absoluta.
const bool USE_ABSOLUTE_FIELD = true;

// Umbral para detectar que pasó un imán.
// Ajusta según tus lecturas reales.
// Si detecta pulsos falsos, súbelo.
// Si no detecta imanes, bájalo.
const int THRESHOLD_ON = 250;

// Umbral para liberar el detector después de pasar un imán.
// Debe ser menor que THRESHOLD_ON para crear histéresis.
const int THRESHOLD_OFF = 120;

// Tiempo mínimo entre pulsos para evitar rebotes o doble detección.
// Con 9 imanes, incluso a velocidad alta esto puede ser bajo.
// 10 ms es conservador.
const uint32_t MIN_PULSE_INTERVAL_US = 10000;

// Si no hay pulsos durante este tiempo, la velocidad se considera 0.
const uint32_t SPEED_TIMEOUT_MS = 1500;

// Cantidad de lecturas para calibrar baseline al inicio
const uint16_t CALIBRATION_SAMPLES = 500;

// Intervalo entre reportes
const uint32_t REPORT_INTERVAL_MS = 1000UL / REPORT_HZ;

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

// Factor de suavizado.
// Más bajo = más suave pero más lento.
// Más alto = más reactivo pero más nervioso.
const float SMOOTH_ALPHA = 0.25;

// =====================================================
// FUNCIONES
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

  Serial.println("# Calibrando sensor Hall...");
  Serial.println("# No muevas la rueda durante este momento, porque aparentemente hasta las bicis necesitan meditar.");

  for (uint16_t i = 0; i < CALIBRATION_SAMPLES; i++) {
    sum += analogRead(HALL_PIN);
    delay(2);
  }

  baseline = sum / CALIBRATION_SAMPLES;

  Serial.print("# Baseline ADC: ");
  Serial.println(baseline);
}

void updateSpeedFromPulse(uint32_t nowUs) {
  currentPulseUs = nowUs;

  if (lastPulseUs > 0) {
    pulseIntervalUs = currentPulseUs - lastPulseUs;

    // Tiempo entre pulsos en segundos
    float pulseIntervalSec = pulseIntervalUs / 1000000.0;

    if (pulseIntervalSec > 0.0) {
      // Pulsos por segundo
      float pulsesPerSecond = 1.0 / pulseIntervalSec;

      // Vueltas por segundo de la rueda
      float revolutionsPerSecond = pulsesPerSecond / NUM_MAGNETS;

      // RPM
      rpm = revolutionsPerSecond * 60.0;

      // Velocidad lineal
      float speedMs = revolutionsPerSecond * WHEEL_CIRCUMFERENCE_M;
      speedKmh = speedMs * 3.6;

      // Suavizado exponencial
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

  // Detectar entrada al campo magnético
  if (!magnetActive && fieldValue >= THRESHOLD_ON) {
    if (lastPulseUs == 0 || (nowUs - lastPulseUs) >= MIN_PULSE_INTERVAL_US) {
      magnetActive = true;
      updateSpeedFromPulse(nowUs);
    }
  }

  // Liberar detección cuando el campo baja
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

void printSerialReport() {
  uint32_t nowMs = millis();

  if (nowMs - lastReportMs >= REPORT_INTERVAL_MS) {
    lastReportMs = nowMs;

    Serial.print(speedKmh, 3);
    Serial.print(",");
    Serial.println(speedSmoothKmh, 3);
  }
}

// =====================================================
// SETUP
// =====================================================

void setup() {
  Serial.begin(SERIAL_BAUD);

  delay(1000);

  Serial.println();
  Serial.println("# bici-interactiva - lector de velocidad ESP32");
  Serial.println("# Formato CSV:");
  Serial.println("# millis,raw,baseline,field,pulse_count,rpm,speed_kmh,speed_smooth_kmh,status");

  analogReadResolution(12);

  // Atenuación para rango aproximado hasta 3.3V.
  // Útil porque el 49E alimentado a 3.3V puede acercarse a esos valores.
  analogSetPinAttenuation(HALL_PIN, ADC_11db);

  calibrateBaseline();

  Serial.print("# Diametro rueda pulgadas: ");
  Serial.println(WHEEL_DIAMETER_INCH);

  Serial.print("# Diametro rueda metros: ");
  Serial.println(WHEEL_DIAMETER_M, 4);

  Serial.print("# Circunferencia rueda metros: ");
  Serial.println(WHEEL_CIRCUMFERENCE_M, 4);

  Serial.print("# Numero de imanes: ");
  Serial.println(NUM_MAGNETS);

  Serial.print("# Radio imanes pulgadas, documentado no usado para velocidad: ");
  Serial.println(MAGNET_RADIUS_INCH);

  Serial.println("# Iniciando lectura...");
}

// =====================================================
// LOOP NO BLOQUEANTE
// =====================================================

void loop() {
  detectMagnetPulse();
  updateTimeout();
  printSerialReport();
}