package com.huylq.iotprojectserver.api;

import com.huylq.iotprojectserver.security.DeviceRegistrationService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/v1/auth/device")
@RequiredArgsConstructor
@Slf4j
public class DeviceRegistrationController {

  private final DeviceRegistrationService registrationService;

  @PostMapping("/register")
  public ResponseEntity<Map<String, Object>> register(@RequestBody Map<String, String> body) {
    String uuid = body.get("device_uuid");
    if (uuid == null || uuid.isBlank()) {
      return ResponseEntity.badRequest().body(Map.of("error", "device_uuid is required"));
    }
    registrationService.registerDevice(uuid);
    log.info("[Security v2.4] Registered device UUID: {}", uuid);
    return ResponseEntity.ok(Map.of("status", "SUCCESS", "registered_device", uuid));
  }

  @PostMapping("/deregister")
  public ResponseEntity<Map<String, Object>> deregister() {
    registrationService.deregisterDevice();
    log.info("[Security v2.4] Deregistered device. Whitelist cleared.");
    return ResponseEntity.ok(Map.of("status", "SUCCESS"));
  }

  @GetMapping("/status")
  public ResponseEntity<Map<String, Object>> status(@RequestHeader(value = "X-Device-UUID", required = false) String uuid) {
    String currentRegistered = registrationService.getRegisteredDeviceUuid();
    if (currentRegistered == null) {
      return ResponseEntity.ok(Map.of(
          "registered", false,
          "has_active_device", false
      ));
    }
    boolean isAllowed = currentRegistered.equals(uuid);
    return ResponseEntity.ok(Map.of(
        "registered", true,
        "is_current_device_allowed", isAllowed,
        "current_registered_device", currentRegistered
    ));
  }
}
