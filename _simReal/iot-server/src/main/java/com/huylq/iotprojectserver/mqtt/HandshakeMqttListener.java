package com.huylq.iotprojectserver.mqtt;

import lombok.extern.slf4j.Slf4j;
import org.eclipse.paho.client.mqttv3.IMqttMessageListener;
import org.eclipse.paho.client.mqttv3.MqttMessage;
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;

@Slf4j
@Component
public class HandshakeMqttListener implements IMqttMessageListener {

  private final MqttClientLifecycle mqttClient;
  private final ObjectMapper json;

  public HandshakeMqttListener(@Lazy MqttClientLifecycle mqttClient, ObjectMapper json) {
    this.mqttClient = mqttClient;
    this.json = json;
  }

  @Override
  public void messageArrived(String topic, MqttMessage message) {
    try {
      String payload = new String(message.getPayload(), StandardCharsets.UTF_8);
      Map<String, Object> data = json.readValue(payload, Map.class);
      String gatewayId = (String) data.get("gateway_id");
      String certHash = (String) data.get("cert_hash");

      log.info("[mTLS] Received Client Hello on topic {} from gateway_id: {}", topic, gatewayId);
      log.info("[mTLS] Gateway Certificate SHA-256 Hash: {}", certHash);

      // Tính toán mã băm mong muốn của gw_hcmc_office_certificate_pem
      MessageDigest digest = MessageDigest.getInstance("SHA-256");
      byte[] hashBytes = digest.digest("gw_hcmc_office_certificate_pem".getBytes(StandardCharsets.UTF_8));
      StringBuilder hexString = new StringBuilder();
      for (byte b : hashBytes) {
        String hex = Integer.toHexString(0xff & b);
        if (hex.length() == 1) hexString.append('0');
        hexString.append(hex);
      }
      String expectedHash = hexString.toString();

      String status = "REJECTED";
      if (expectedHash.equalsIgnoreCase(certHash)) {
        status = "APPROVED";
        log.info("[mTLS] Client Certificate Verification SUCCESS. Gateway approved.");
      } else {
        log.warn("[SECURITY ALERT] Client Certificate Verification FAILED. Expected: {}, Got: {}", expectedHash, certHash);
      }

      String responsePayload = json.writeValueAsString(Map.of(
          "gateway_id", gatewayId != null ? gatewayId : "unknown",
          "status", status
      ));

      log.info("[mTLS] Sending Server Hello & Verification status ({}) to topic iot/handshake/server", status);
      mqttClient.publish("iot/handshake/server", responsePayload.getBytes(StandardCharsets.UTF_8), 1, false);

    } catch (Exception e) {
      log.error("[mTLS] Error processing handshake message", e);
    }
  }
}
