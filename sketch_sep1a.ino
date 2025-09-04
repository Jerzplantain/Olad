// --- Fix Arduino auto-prototype issue:
struct Sample;   // forward declaration

// ====== ESP32 + TWAI (CAN) + Supabase OBD-II Logger ======
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <WiFiClientSecure.h>
#include "driver/twai.h"
#include <math.h>
#include <map>
#include <array>

// ---- Safely detect ESP-IDF major version ----
#if defined(__has_include)
  #if __has_include("esp_idf_version.h")
    #include "esp_idf_version.h"
  #else
    #define ESP_IDF_VERSION_MAJOR 4
  #endif
#else
  #define ESP_IDF_VERSION_MAJOR 4
#endif

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

// ---------- TWAI compat (IDF 4.4 vs 5.x) ----------
#if ESP_IDF_VERSION_MAJOR >= 5
  #define TWAI_SET_EXTD(msg, is_ext)   do { (msg).flags = (is_ext) ? TWAI_MSG_FLAG_EXTD : 0; } while(0)
  #define TWAI_IS_EXTD(msg)            (((msg).flags & TWAI_MSG_FLAG_EXTD) != 0)
#else
  #define TWAI_SET_EXTD(msg, is_ext)   do { (msg).extd = (is_ext); (msg).rtr = 0; (msg).ss = 0; (msg).self = 0; } while(0)
  #define TWAI_IS_EXTD(msg)            ((msg).extd)
#endif

// ---- Alert shims ----
#ifdef TWAI_ALERT_RECOVERY_COMPLETE
  #define TWAI_ALERT_RECOVERY_COMPLETE_IFDEF TWAI_ALERT_RECOVERY_COMPLETE
#else
  #define TWAI_ALERT_RECOVERY_COMPLETE_IFDEF 0
#endif
#ifdef TWAI_ALERT_RECOVERY_IN_PROGRESS
  #define TWAI_ALERT_RECOVERY_IN_PROGRESS_IFDEF TWAI_ALERT_RECOVERY_IN_PROGRESS
#else
  #define TWAI_ALERT_RECOVERY_IN_PROGRESS_IFDEF 0
#endif

// ===== USER CONFIG =====
#define OBD_BITRATE_500K 1
#if OBD_BITRATE_500K
  #define TWAI_TIMING   TWAI_TIMING_CONFIG_500KBITS()
#else
  #define TWAI_TIMING   TWAI_TIMING_CONFIG_250KBITS()
#endif

const unsigned long MIN_UPLOAD_INTERVAL_MS = 5000;
const unsigned long MAX_UPLOAD_INTERVAL_MS = 60000;

// Change thresholds
const float THRESH_RPM      = 50.0f;
const float THRESH_COOLANT  = 1.0f;
const float THRESH_BATT     = 0.10f;
const float THRESH_STFT     = 1.0f;
const float THRESH_LTFT     = 0.5f;

// Raw frame sampling
#define ENABLE_RAW_SAMPLING      1
const unsigned long RAW_SAMPLE_EVERY_MS = 10000;

// Extended functional requests
#define SEND_EXTENDED_REQUESTS 0

// ===== Wi-Fi =====
const char* ssids[]     = {"Galaxy"};
const char* passwords[] = {"american"};
const int networkCount  = sizeof(ssids) / sizeof(ssids[0]);

// ===== Supabase =====
String serverUrl   = "https://zhrlppnknfjxhwhfsdxd.supabase.co/rest/v1/sensor_data";
String rawUrl      = "https://zhrlppnknfjxhwhfsdxd.supabase.co/rest/v1/can_raw";
String SUPABASE_KEY= "<eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpocmxwcG5rbmZqeGh3aGZzZHhkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTY1NjY3NjIsImV4cCI6MjA3MjE0Mjc2Mn0.EVrzx09YwDglwFUCjS3hKbrg2Wdy1hjSPV1gWxnN_yU>";
String vehicle_id  = "NJ test facility 01";

// ===== Pins =====
const int LED_PIN = 2;
const int RX_PIN  = 21;
const int TX_PIN  = 22;

// ===== Upload types =====
struct Sample {
  float batt      = NAN;  // PID 0x42
  float coolant   = NAN;  // 0x05
  float rpm       = NAN;  // 0x0C
  float stft_b1   = NAN;  // 0x06
  float ltft_b1   = NAN;  // 0x07
  float stft_b2   = NAN;  // 0x08
  float ltft_b2   = NAN;  // 0x09
  long  runtime_s = -1;   // 0x1F
};

inline bool valid(float v) { return !isnan(v); }

// ===== WiFi =====
void connectWiFi() {
  for (int i = 0; i < networkCount; i++) {
    Serial.printf("Trying WiFi: %s\n", ssids[i]);
    WiFi.begin(ssids[i], passwords[i]);
    int attempt = 0;
    while (WiFi.status() != WL_CONNECTED && attempt++ < 30) {
      digitalWrite(LED_PIN, HIGH); delay(250);
      digitalWrite(LED_PIN, LOW);  delay(250);
    }
    if (WiFi.status() == WL_CONNECTED) {
      Serial.printf("\n✅ Connected to %s\n", ssids[i]);
      Serial.print("IP: "); Serial.println(WiFi.localIP());
      digitalWrite(LED_PIN, HIGH);
      return;
    }
  }
  Serial.println("\n❌ Failed to connect to WiFi!");
}

// ===== HTTPS helper =====
bool postJson(const String& url, const String& jsonPayload) {
  Serial.println("=== SUPABASE POST DEBUG ===");
  Serial.print("URL: "); Serial.println(url);
  Serial.print("Payload: "); Serial.println(jsonPayload);
  Serial.println("===========================");

  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient http;
  if (!http.begin(client, url)) {
    Serial.println("HTTP begin failed");
    return false;
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("apikey", SUPABASE_KEY);
  http.addHeader("Authorization", String("Bearer ") + SUPABASE_KEY);
  http.addHeader("Prefer", "return=representation");

  int status = http.POST(jsonPayload);
  Serial.printf("HTTP status: %d\n", status);
  String resp = http.getString();
  Serial.print("Response body: "); Serial.println(resp);

  http.end();
  return (status >= 200 && status < 300);
}

// ===== Upload helpers =====
void sendData(const Sample& s) {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
    if (WiFi.status() != WL_CONNECTED) return;
  }

  StaticJsonDocument<600> doc;
  doc["vehicle_id"] = vehicle_id;
  doc["timestamp"] = millis();

  doc["battery_voltage"] = valid(s.batt) ? s.batt : 0;
  doc["engine_coolant_temp"] = valid(s.coolant) ? s.coolant : 0;
  doc["coolant_temperature"] = valid(s.coolant) ? s.coolant : 0;
  doc["engine_rpms"] = valid(s.rpm) ? s.rpm : 0;
  doc["engine_runtime_s"] = s.runtime_s >= 0 ? s.runtime_s : 0;
  doc["time_since_engine_start"] = s.runtime_s >= 0 ? s.runtime_s : 0;

  doc["stft_b1_pct"] = valid(s.stft_b1) ? s.stft_b1 : 0;
  doc["ltft_b1_pct"] = valid(s.ltft_b1) ? s.ltft_b1 : 0;
  doc["stft_b2_pct"] = valid(s.stft_b2) ? s.stft_b2 : 0;
  doc["ltft_b2_pct"] = valid(s.ltft_b2) ? s.ltft_b2 : 0;

  doc["short_term_fuel_trim_b1"] = valid(s.stft_b1) ? s.stft_b1 : 0;
  doc["short_term_fuel_trim_b2"] = valid(s.stft_b2) ? s.stft_b2 : 0;

  doc["fuel_trim"] = 0;
  doc["alert"] = "{}";
  doc["anomaly_score"] = "{}";

  String payload; serializeJson(doc, payload);
  bool ok = postJson(serverUrl, payload);
  Serial.printf("📡 PID Upload %s\n", ok ? "OK" : "FAIL");
}

// ===== RAW frame logging =====
struct RawCache {
  unsigned long lastUpload = 0;
  std::array<uint8_t, 8> lastData{};
};
std::map<uint32_t, RawCache> rawCache;

void sendRawFrame(uint32_t packetId, bool isExt, const uint8_t *buf, int len) {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
    if (WiFi.status() != WL_CONNECTED) return;
  }

  StaticJsonDocument<256> doc;
  doc["vehicle_id"]  = vehicle_id;
  doc["can_id"]      = packetId;
  doc["is_extended"] = isExt;
  doc["dlc"]         = len;

  JsonArray dataArr = doc.createNestedArray("data");
  for (int i = 0; i < len; i++) dataArr.add(buf[i]);

  String payload; serializeJson(doc, payload);
  bool ok = postJson(rawUrl, payload);
  Serial.printf("📡 RAW Upload %s\n", ok ? "OK" : "FAIL");
}

// ===== OBD-II helpers =====
bool sendOBDRequest(uint32_t id, bool extended, uint8_t pid) {
  twai_message_t msg = {};
  msg.identifier = id;
  msg.data_length_code = 8;
  msg.data[0] = 0x02;
  msg.data[1] = 0x01;
  msg.data[2] = pid;
  for (int i = 3; i < 8; i++) msg.data[i] = 0x00;
  TWAI_SET_EXTD(msg, extended);

  esp_err_t err = twai_transmit(&msg, pdMS_TO_TICKS(50));
  if (err != ESP_OK) {
    Serial.printf("❌ twai_transmit failed (0x%X)\n", err);
    return false;
  }
  Serial.printf("📤 Sent %s PID 0x%02X on ID 0x%X\n", extended ? "EXT" : "STD", pid, id);
  return true;
}

float parsePID(uint32_t can_id, bool isExt, const uint8_t *d, int len, uint8_t pid) {
  bool idMatch = (!isExt && (can_id >= 0x7E8 && can_id <= 0x7EF))
              || (isExt && (can_id == 0x18DAF110));
  if (!idMatch || len < 5 || d[1] != 0x41 || d[2] != pid) return NAN;

  uint8_t A = d[3], B = d[4];
  switch (pid) {
    case 0x42: return ((A * 256.0f) + B) / 1000.0f;
    case 0x05: return (float)A - 40.0f;
    case 0x0C: return ((A * 256.0f) + B) / 4.0f;
    case 0x06: case 0x07: case 0x08: case 0x09:
      return ((float)A - 128.0f) * (100.0f / 128.0f);
    case 0x1F: return (A * 256.0f) + B;
  }
  return NAN;
}

// ===== TWAI init =====
bool twaiInit() {
  twai_general_config_t g_config = TWAI_GENERAL_CONFIG_DEFAULT((gpio_num_t)TX_PIN, (gpio_num_t)RX_PIN, TWAI_MODE_NORMAL);
  twai_timing_config_t  t_config = TWAI_TIMING;
  twai_filter_config_t  f_config = TWAI_FILTER_CONFIG_ACCEPT_ALL();
  g_config.rx_queue_len = 20;
  g_config.tx_queue_len = 10;

  if (twai_driver_install(&g_config, &t_config, &f_config) != ESP_OK) {
    Serial.println("❌ twai_driver_install failed");
    return false;
  }
  if (twai_start() != ESP_OK) {
    Serial.println("❌ twai_start failed");
    return false;
  }
  Serial.printf("✅ TWAI started at %s kbps\n", OBD_BITRATE_500K ? "500" : "250");

  uint32_t alerts = TWAI_ALERT_RX_DATA | TWAI_ALERT_ERR_PASS | TWAI_ALERT_BUS_OFF |
                    TWAI_ALERT_TX_FAILED | TWAI_ALERT_RX_QUEUE_FULL |
                    TWAI_ALERT_RECOVERY_COMPLETE_IFDEF | TWAI_ALERT_RECOVERY_IN_PROGRESS_IFDEF;
  twai_reconfigure_alerts(alerts, nullptr);

  twai_status_info_t st;
  twai_get_status_info(&st);
  Serial.printf("TWAI status: state=%d tx_q=%d rx_q=%d tx_err=%d rx_err=%d bus_errs=%d\n",
                st.state, st.msgs_to_tx, st.msgs_to_rx, st.tx_error_counter, st.rx_error_counter, st.bus_error_count);
  return true;
}

// ===== Upload gating =====
Sample lastSent;
unsigned long lastUploadAt = 0;

bool changedEnough(const Sample& prev, const Sample& cur) {
  auto ch = [](float a, float b, float thr) {
    if (!valid(a) || !valid(b)) return false;
    return fabsf(a - b) >= thr;
  };
  return ch(prev.batt,     cur.batt,     THRESH_BATT)   ||
         ch(prev.coolant,  cur.coolant,  THRESH_COOLANT)||
         ch(prev.rpm,      cur.rpm,      THRESH_RPM)    ||
         ch(prev.stft_b1,  cur.stft_b1,  THRESH_STFT)   ||
         ch(prev.ltft_b1,  cur.ltft_b1,  THRESH_LTFT)   ||
         ch(prev.stft_b2,  cur.stft_b2,  THRESH_STFT)   ||
         ch(prev.ltft_b2,  cur.ltft_b2,  THRESH_LTFT);
}

bool shouldUpload(const Sample& prev, const Sample& cur, unsigned long now) {
  bool time_ok   = (now - lastUploadAt) >= MIN_UPLOAD_INTERVAL_MS;
  bool keepalive = (now - lastUploadAt) >= MAX_UPLOAD_INTERVAL_MS;
  if (keepalive) return true;
  if (!time_ok)  return false;
  return changedEnough(prev, cur);
}

// ================== Setup ==================
void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  connectWiFi();
  if (!twaiInit()) {
    Serial.println("HALT: TWAI init failed");
    while (1) { digitalWrite(LED_PIN, !digitalRead(LED_PIN)); delay(500); }
  }
}

// ================== Loop ==================
void loop() {
  // 1) Send Mode 01 requests
  sendOBDRequest(0x7DF, false, 0x42); // battery
  sendOBDRequest(0x7DF, false, 0x05); // coolant
  sendOBDRequest(0x7DF, false, 0x0C); // RPM
  sendOBDRequest(0x7DF, false, 0x1F); // runtime
  sendOBDRequest(0x7DF, false, 0x06); // STFT B1
  sendOBDRequest(0x7DF, false, 0x07); // LTFT B1
  sendOBDRequest(0x7DF, false, 0x08); // STFT B2
  sendOBDRequest(0x7DF, false, 0x09); // LTFT B2

#if SEND_EXTENDED_REQUESTS
  sendOBDRequest(0x18DB33F1, true,  0x42);
  sendOBDRequest(0x18DB33F1, true,  0x05);
  sendOBDRequest(0x18DB33F1, true,  0x0C);
  sendOBDRequest(0x18DB33F1, true,  0x1F);
  sendOBDRequest(0x18DB33F1, true,  0x06);
  sendOBDRequest(0x18DB33F1, true,  0x07);
  sendOBDRequest(0x18DB33F1, true,  0x08);
  sendOBDRequest(0x18DB33F1, true,  0x09);
#endif

  delay(100);

  // 2) Read responses for ~500 ms and decode
  Sample cur;  // defaults: NaNs/-1
  unsigned long start = millis();
  twai_message_t rx_msg;

  while (millis() - start < 500) {
    if (twai_receive(&rx_msg, pdMS_TO_TICKS(10)) == ESP_OK) {
      bool isExt   = TWAI_IS_EXTD(rx_msg);
      int  len     = rx_msg.data_length_code;
      uint32_t id  = rx_msg.identifier;

      Serial.printf("⬇️ RX %s ID: 0x%X  LEN: %d  Data:", isExt ? "EXT" : "STD", id, len);
      for (int i = 0; i < len; i++) Serial.printf(" %02X", rx_msg.data[i]);
      Serial.println();

      // Parse known PIDs
      float v;
      v = parsePID(id, isExt, rx_msg.data, len, 0x42); if (!isnan(v)) cur.batt      = v;
      v = parsePID(id, isExt, rx_msg.data, len, 0x05); if (!isnan(v)) cur.coolant   = v;
      v = parsePID(id, isExt, rx_msg.data, len, 0x0C); if (!isnan(v)) cur.rpm       = v;
      v = parsePID(id, isExt, rx_msg.data, len, 0x06); if (!isnan(v)) cur.stft_b1   = v;
      v = parsePID(id, isExt, rx_msg.data, len, 0x07); if (!isnan(v)) cur.ltft_b1   = v;
      v = parsePID(id, isExt, rx_msg.data, len, 0x08); if (!isnan(v)) cur.stft_b2   = v;
      v = parsePID(id, isExt, rx_msg.data, len, 0x09); if (!isnan(v)) cur.ltft_b2   = v;
      v = parsePID(id, isExt, rx_msg.data, len, 0x1F); if (!isnan(v)) cur.runtime_s = (long)v;

      // --- Optimized raw CAN logging ---
#if ENABLE_RAW_SAMPLING
      unsigned long nowRaw = millis();
      uint32_t key = (isExt ? 0x80000000 : 0) | id;  // unique key per ID + ext flag
      RawCache &entry = rawCache[key];

      std::array<uint8_t, 8> currentData{};
      memcpy(currentData.data(), rx_msg.data, len);

      bool dataChanged = (currentData != entry.lastData);
      bool timeExceeded = (nowRaw - entry.lastUpload >= RAW_SAMPLE_EVERY_MS);

      if (dataChanged || timeExceeded) {
        entry.lastData = currentData;
        entry.lastUpload = nowRaw;
        sendRawFrame(id, isExt, rx_msg.data, len);
      }
#endif
    }
  }

  // 3) Upload PID data if changed enough
  unsigned long now = millis();
  if (shouldUpload(lastSent, cur, now)) {
    sendData(cur);
    lastSent     = cur;
    lastUploadAt = now;
  }

  // 4) Bus health alerts
  uint32_t al = 0;
  if (twai_read_alerts(&al, 0) == ESP_OK && al) {
    Serial.print("TWAI alerts:");
    if (al & TWAI_ALERT_RX_DATA)                    Serial.print(" RX_DATA");
    if (al & TWAI_ALERT_TX_FAILED)                  Serial.print(" TX_FAILED");
    if (al & TWAI_ALERT_RX_QUEUE_FULL)              Serial.print(" RX_QUEUE_FULL");
    if (al & TWAI_ALERT_ERR_PASS)                   Serial.print(" ERR_PASS");
    if (al & TWAI_ALERT_BUS_OFF)                    Serial.print(" BUS_OFF");
    if (al & TWAI_ALERT_RECOVERY_COMPLETE_IFDEF)    Serial.print(" RECOVERY_COMPLETE");
    if (al & TWAI_ALERT_RECOVERY_IN_PROGRESS_IFDEF) Serial.print(" RECOVERY_IN_PROGRESS");
    Serial.println();
  }

  delay(500);
}
