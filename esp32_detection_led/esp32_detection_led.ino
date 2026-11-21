#include <Arduino.h>
#include <WiFi.h>
#include <atomic>
#include <esp_idf_version.h>
#include <esp_now.h>
#include <esp_wifi.h>

// GPIO 27 HIGH selects the receiver. An unconnected pin selects the USB sender.
constexpr int kRolePin = 27;
constexpr uint8_t kChannel = 1;
constexpr int kLedPin = 2;
constexpr int kBuzzerPin = 26;
constexpr unsigned int kBuzzerHz = 3000;
constexpr int kLedOn = HIGH;
constexpr int kLedOff = kLedOn == HIGH ? LOW : HIGH;
constexpr unsigned long kBlinkMs = 180;
const uint8_t kBroadcast[] = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff};
const uint8_t kBlinkPacket[] = {'C', 'U', 'R', 'L', '1'};

std::atomic<bool> remoteBlink{false};
bool usbSender = true;
bool radioReady = false;
bool blinking = false;
unsigned long blinkStarted = 0;

#if ESP_IDF_VERSION_MAJOR >= 5
void receiveBlink(const esp_now_recv_info_t *, const uint8_t *data, int length) {
#else
void receiveBlink(const uint8_t *, const uint8_t *data, int length) {
#endif
  if (length == sizeof(kBlinkPacket) && memcmp(data, kBlinkPacket, sizeof(kBlinkPacket)) == 0) {
    remoteBlink.store(true);
  }
}

bool setupRadio() {
  if (!WiFi.mode(WIFI_STA) ||
      esp_wifi_set_channel(kChannel, WIFI_SECOND_CHAN_NONE) != ESP_OK ||
      esp_now_init() != ESP_OK) {
    return false;
  }

  if (!usbSender) {
    return esp_now_register_recv_cb(receiveBlink) == ESP_OK;
  }

  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, kBroadcast, sizeof(kBroadcast));
  peer.channel = kChannel;
  peer.ifidx = WIFI_IF_STA;
  return esp_now_add_peer(&peer) == ESP_OK;
}

void startBlink() {
  if (!usbSender) {
    tone(kBuzzerPin, kBuzzerHz);
  }
  digitalWrite(kLedPin, kLedOn);
  blinkStarted = millis();
  blinking = true;
}

void setup() {
  pinMode(kBuzzerPin, OUTPUT);
  digitalWrite(kBuzzerPin, LOW);
  pinMode(kRolePin, INPUT_PULLDOWN);
  usbSender = digitalRead(kRolePin) == LOW;

  pinMode(kLedPin, OUTPUT);
  digitalWrite(kLedPin, kLedOff);
  Serial.begin(115200);
  radioReady = setupRadio();

  for (int pulse = 0; pulse < 3; ++pulse) {
    digitalWrite(kLedPin, kLedOn);
    delay(150);
    digitalWrite(kLedPin, kLedOff);
    delay(150);
  }
  if (!radioReady) {
    Serial.println("ESP-NOW setup failed");
  } else {
    Serial.println(usbSender ? "READY: USB sender" : "READY: ESP-NOW receiver");
  }
}

void loop() {
  if (usbSender) {
    while (Serial.available() > 0) {
      if (Serial.read() == 'B') {
        startBlink();
        Serial.println("BLINK");
        if (radioReady && esp_now_send(kBroadcast, kBlinkPacket, sizeof(kBlinkPacket)) != ESP_OK) {
          Serial.println("ESP-NOW send failed");
        }
      }
    }
  } else if (remoteBlink.exchange(false)) {
    Serial.println("ESP-NOW BLINK RECEIVED");
    startBlink();
  }

  if (blinking && millis() - blinkStarted >= kBlinkMs) {
    digitalWrite(kLedPin, kLedOff);
    if (!usbSender) {
      noTone(kBuzzerPin);
      digitalWrite(kBuzzerPin, LOW);
    }
    blinking = false;
  }
}





