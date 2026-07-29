package com.huylq.iotprojectserver.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import java.util.concurrent.atomic.AtomicReference;

@Service
public class DeviceRegistrationService {

  private final AtomicReference<String> registeredDeviceUuid;

  public DeviceRegistrationService(
      @Value("${app.security.default-device-uuid:none}") String defaultUuid) {
    this.registeredDeviceUuid = new AtomicReference<>("none".equalsIgnoreCase(defaultUuid) ? null : defaultUuid);
  }

  public void registerDevice(String uuid) {
    registeredDeviceUuid.set(uuid);
  }

  public void deregisterDevice() {
    registeredDeviceUuid.set(null);
  }

  public String getRegisteredDeviceUuid() {
    return registeredDeviceUuid.get();
  }

  public boolean isAllowed(String uuid) {
    String currentRegistered = registeredDeviceUuid.get();
    // Nếu không cấu hình thiết bị đăng ký thì cho phép truy cập tự do
    if (currentRegistered == null) {
      return true;
    }
    return currentRegistered.equals(uuid);
  }
}
