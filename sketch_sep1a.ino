#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "driver/twai.h"

// --- WiFi credentials ---
const char* ssids[]     = {"Galaxy"};
const char* passwords[] = {"american"};
const int networkCount  = sizeof(ssids) / sizeof(ssids[0]);

// --- LED ---
const int LED_PIN = 2;

// --- CAN/TWAI config ---
const int CAN_RX_PIN = 21;
const int CAN_TX_PIN = 22;
const uint32_t CAN_BITRATE_KBPS = 500;

// --- Supabase ---
String serverUrl = "https://zhrlppnknfjxhwhfsdxd.supabase.co/rest/v1/sensor_data";
String rawUrl    = "https://zhrlppnknfjxhwhfsdxd.supabase.co/rest/v1/can_raw";
String SUPABASE_KEY = "YOUR_SUPABASE_ANON_KEY";
String vehicle_id = "ESP32_CAN_Car01";

// --- TWAI init ---
bool twai_init(uint32_t bitrate_kbps, int rx, int tx) {
  twai_general_config_t g_config = TWAI_GENERAL_CONFIG_DEFAULT((gpio_num_t)tx, (gpio_num_t)rx, TWAI_MODE_NORMAL);

  twai_timing_config_t t_config;
  switch (bitrate_kbps) {
    case 125:  t_config = TWAI_TIMING_CONFIG_125KBITS(); break;
    case 250:  t_config = TWAI_TIMING_CONFIG_250KBITS(); break;
    case 500:  t_config = TWAI_TIMING_CONFIG_500KBITS(); break;
    case 1000: t_config = TWAI_TIMING_CONFIG_1MBITS(); break;
    default:   t_config = TWAI_TIMING_CONFIG_500KBITS(); break;
  }

  twai_filter_config_t f_config = TWAI_FILTER_CONFIG_ACCEPT_ALL();

  if (twai_driver_install(&g_config, &t_config, &f_config) != ESP_OK) return false;
  if (twai_start() != ESP_OK) { twai_driver_uninstall(); return false; }
  Serial.println("TWAI initialized");
  return true;
}

// --- WiFi connect ---
void connectWiFiWithLED() {
  pinMode(LED_PIN, OUTPUT);
  WiFi.mode(WIFI_STA);

  bool connected = false;
  for (int i = 0; i < networkCount && !connected; i++) {
    Serial.printf("Connecting to SSID: %s\n", ssids[i]);
    WiFi.begin(ssids[i], passwords[i]);

    unsigned long startAttempt = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - startAttempt < 10000) {
      digitalWrite(LED_PIN, !digitalRead(LED_PIN)); delay(250);
    }
    if (WiFi.status() == WL_CONNECTED) connected = true;
  }

  if (connected) { digitalWrite(LED_PIN, HIGH); Serial.println("✅ WiFi connected"); }
  else { Serial.println("❌ WiFi failed"); digitalWrite(LED_PIN, LOW); }
}

// --- Supabase POST ---
bool postJson(const String& url, const String& jsonPayload) {
  WiFiClientSecure client; client.setInsecure();
  HTTPClient http;
  if (!http.begin(client, url)) return false;

  http.addHeader("Content-Type", "application/json");
  http.addHeader("apikey", SUPABASE_KEY);
  http.addHeader("Authorization", "Bearer " + SUPABASE_KEY);

  int status = http.POST(jsonPayload);
  Serial.printf("HTTP POST status: %d\n", status);
  http.end();
  return (status >= 200 && status < 300);
}

// --- Send wide sensor payload ---
void sendWideData(float battery_voltage, float fuel_trim, float alternator, float misfire,
                  float rpm, float run_time, float coolant, float oil_temp, float trans_temp) {
  if (WiFi.status() != WL_CONNECTED) connectWiFiWithLED();
  if (WiFi.status() != WL_CONNECTED) return;

  StaticJsonDocument<1024> doc;
  doc["vehicle_id"] = vehicle_id;
  doc["timestamp"]  = String(millis()); // or use RTC if available
  doc["battery_voltage"]       = battery_voltage;
  doc["fuel_trim"]             = fuel_trim;
  doc["alternator_output"]     = alternator;
  doc["misfire_count"]         = misfire;
  doc["engine_rpms"]           = rpm;
  doc["engine_run_time"]       = run_time;
  doc["coolant_temperature"]   = coolant;
  doc["engine_oil_temperature"]= oil_temp;
  doc["transmission_oil_temperature"] = trans_temp;

  String payload; serializeJson(doc, payload);
  postJson(serverUrl, payload);
}

// --- Send unknown raw CAN ---
void sendRawFrame(int id, bool isExt, uint8_t* buf, int len) {
  if (WiFi.status() != WL_CONNECTED) connectWiFiWithLED();
  if (WiFi.status() != WL_CONNECTED) return;

  StaticJsonDocument<512> doc;
  doc["vehicle_id"] = vehicle_id;
  doc["can_id"]     = id;
  doc["is_extended"]= isExt;
  JsonArray arr = doc.createNestedArray("data");
  for (int i = 0; i < len; i++) arr.add(buf[i]);

  String payload; serializeJson(doc, payload);
  postJson(rawUrl, payload);
}

// --- Decoding function (OBD-II) ---
void decodeAndSend(const twai_message_t &msg) {
  // initialize values as -1 (unknown)
  static float battery_voltage=-1, fuel_trim=-1, alternator=-1, misfire=-1,
               rpm=-1, run_time=-1, coolant=-1, oil_temp=-1, trans_temp=-1;

  if (msg.identifier == 0x7E8 && msg.data_length_code >= 5) {
    uint8_t pid = msg.data[2];
    switch(pid) {
      case 0x0C: rpm = ((msg.data[3]<<8)|msg.data[4])/4.0; break; // RPM
      case 0x05: coolant = msg.data[3]-40.0; break;                // Coolant temp
      case 0x0D: /* speed if needed */ break;
      case 0x0F: /* intake air temp */ break;
      case 0x42: battery_voltage = msg.data[3]*0.1; break;
      case 0x06: fuel_trim = (msg.data[3]*256 + msg.data[4])/1.28; break; // example scaling
      case 0x46: misfire = msg.data[3]; break;                     // Misfire count
      case 0x47: alternator = msg.data[3]*0.1; break;             // Alternator
      case 0x5C: oil_temp = msg.data[3]-40; break;               // Engine oil temp
      case 0x5E: trans_temp = msg.data[3]-40; break;             // Transmission temp
      default: sendRawFrame(msg.identifier, msg.extd, (uint8_t*)msg.data, msg.data_length_code); break;
    }
    sendWideData(battery_voltage, fuel_trim, alternator, misfire,
                 rpm, run_time, coolant, oil_temp, trans_temp);
  } else {
    sendRawFrame(msg.identifier, msg.extd, (uint8_t*)msg.data, msg.data_length_code);
  }
}

// --- Setup ---
void setup() {
  Serial.begin(115200);
  delay(200);
  pinMode(LED_PIN, OUTPUT);
  connectWiFiWithLED();
  if(!twai_init(CAN_BITRATE_KBPS, CAN_RX_PIN, CAN_TX_PIN)) Serial.println("TWAI init failed");
}

// --- Loop ---
void loop() {
  twai_message_t message;
  if(twai_receive(&message, pdMS_TO_TICKS(10)) == ESP_OK) decodeAndSend(message);

  // LED status
  if(WiFi.status() != WL_CONNECTED) digitalWrite(LED_PIN, millis()%500<250?HIGH:LOW);
  else digitalWrite(LED_PIN, HIGH);
}
