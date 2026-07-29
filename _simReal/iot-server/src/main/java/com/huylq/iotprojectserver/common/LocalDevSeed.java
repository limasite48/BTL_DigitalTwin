package com.huylq.iotprojectserver.common;

import com.huylq.iotprojectserver.alert.Alert;
import com.huylq.iotprojectserver.alert.AlertRepository;
import com.huylq.iotprojectserver.command.DeviceState;
import com.huylq.iotprojectserver.command.DeviceStateRepository;
import com.huylq.iotprojectserver.command.Command;
import com.huylq.iotprojectserver.command.CommandRepository;
import com.huylq.iotprojectserver.common.time.Clocks;
import com.huylq.iotprojectserver.health.DeviceHealth;
import com.huylq.iotprojectserver.health.DeviceHealthRepository;
import com.huylq.iotprojectserver.registry.Device;
import com.huylq.iotprojectserver.registry.DeviceRepository;
import com.huylq.iotprojectserver.registry.Sensor;
import com.huylq.iotprojectserver.registry.SensorRepository;
import com.huylq.iotprojectserver.rules.Rule;
import com.huylq.iotprojectserver.rules.RuleRepository;
import com.huylq.iotprojectserver.security.Role;
import com.huylq.iotprojectserver.security.user.User;
import com.huylq.iotprojectserver.security.user.UserRepository;
import com.huylq.iotprojectserver.telemetry.SensorLatest;
import com.huylq.iotprojectserver.telemetry.SensorLatestRepository;
import com.huylq.iotprojectserver.telemetry.Telemetry;
import com.huylq.iotprojectserver.telemetry.TelemetryRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.transaction.support.TransactionTemplate;
import tools.jackson.databind.ObjectMapper;

import java.time.OffsetDateTime;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Seed data for the {@code local} profile so the schema isn't empty after a fresh boot.
 */
@Slf4j
@Profile("local")
@Configuration
@RequiredArgsConstructor
public class LocalDevSeed {

  private final DeviceRepository deviceRepo;
  private final SensorRepository sensorRepo;
  private final UserRepository userRepo;
  private final PasswordEncoder passwordEncoder;
  private final TelemetryRepository telemetryRepo;
  private final SensorLatestRepository sensorLatestRepo;
  private final DeviceHealthRepository deviceHealthRepo;
  private final CommandRepository commandRepo;
  private final DeviceStateRepository deviceStateRepo;
  private final RuleRepository ruleRepo;
  private final AlertRepository alertRepo;
  private final TransactionTemplate txTemplate;
  private final ObjectMapper json;

  private static final String PRESET_PASSWORD = "changeme";

  @Bean
  ApplicationRunner seedFixtures() {
    log.info("Configuring local dev seed");
    long startMs = System.currentTimeMillis();
    return args -> txTemplate.executeWithoutResult(tx -> {
      seedUsers();
      seedDevices();
      seedRules();
      seedCommandsAndDeviceState();
      log.info("Seeded local dev fixtures in {}ms", System.currentTimeMillis() - startMs);
    });
  }

  void seedUsers() {
    long startMs = System.currentTimeMillis();
    log.info("Seeding local dev users (existing usernames untouched)");

    saveUser("admin", Role.SUPER_ADMIN);
    saveUser("manager", Role.ADMIN);
    saveUser("operator", Role.OPERATOR);
    saveUser("tech", Role.TECHNICIAN);
    saveUser("user", Role.VIEWER);

    log.info("Seeded users in {}ms", System.currentTimeMillis() - startMs);
  }

  void seedDevices() {
    long startMs = System.currentTimeMillis();
    log.info("Seeding local dev devices (existing ids untouched)");

    // Single gateway for HCMC Office
    Device gw = saveGateway("gw_hcmc_office", "connect", Device.Status.ACTIVE);

    // Seed the 12 zones:
    String[] zones = {
        "pantry", "storage", "prvt_meeting", "office_1", "office_2", "lobby", 
        "connect", "director", "finance_mng", "meeting", "technical_mng", "vice_director"
    };

    for (String zone : zones) {
      String zId = zone.equals("office_1") ? "office01" : (zone.equals("office_2") ? "office02" : zone);
      // Sensors:
      saveSensor("s_" + zId + "_dht22", "dht22", zone, gw);
      saveSensor("s_" + zId + "_mq2", "mq2", zone, gw);
      saveSensor("s_" + zId + "_lm393", "lm393", zone, gw);
      
      // Devices:
      saveDevice("d_" + zId + "_light", "light", zone, Device.Status.ACTIVE);
      saveDevice("d_" + zId + "_ahu", "ac", zone, Device.Status.ACTIVE);
    }

    // Door sensors (5 doors):
    for (int i = 1; i <= 5; i++) {
      String doorZone = i == 3 ? "director" : (i == 5 ? "vice_director" : (i == 4 ? "meeting" : "lobby"));
      saveSensor("s_door0" + i + "_mc38", "mc38", doorZone, gw);
    }

    // Window sensors (6 windows):
    String[] windowZones = {"lobby", "office_1", "office_2", "director", "meeting", "vice_director"};
    for (int i = 1; i <= 6; i++) {
      String wZone = windowZones[i - 1];
      saveSensor("s_wd0" + i + "_mc38", "mc38", wZone, gw);
      saveDevice("d_wd0" + i + "_curtain", "curtain", wZone, Device.Status.ACTIVE);
    }

    log.info("Seeded devices in {}ms", System.currentTimeMillis() - startMs);
  }

  void seedTelemetryAndCurrentState() {
    if (telemetryRepo.count() > 0) {
      log.debug("Telemetry already present — skipping telemetry seed");
      return;
    }
    long startMs = System.currentTimeMillis();
    log.info("Seeding local dev telemetry history + current state");

    record Series(String sensorId, String type, String zone, String gatewayId,
                  double base, double amplitude, String unit) { }
    List<Series> numeric = List.of(
        new Series("s_office01_dht22", "temp", "office_1", "gw_hcmc_office", 23.0, 2.5, "C"),
        new Series("s_office01_dht22", "hmid", "office_1", "gw_hcmc_office", 55.0, 8.0, "%"),
        new Series("s_meeting_dht22", "temp", "meeting", "gw_hcmc_office", 25.0, 3.0, "C"),
        new Series("s_meeting_dht22", "hmid", "meeting", "gw_hcmc_office", 60.0, 6.0, "%"));

    OffsetDateTime now = Clocks.nowUtc();
    OffsetDateTime monthStart = now.withDayOfMonth(1).truncatedTo(ChronoUnit.DAYS);

    int steps = 36;
    List<Telemetry> rows = new ArrayList<>();
    for (int i = steps; i >= 0; i--) {
      OffsetDateTime ts = now.minusMinutes(10L * i);
      if (ts.isBefore(monthStart)) {
        continue;
      }
      double phase = Math.sin(2 * Math.PI * (steps - i) / (double) steps);
      for (Series s : numeric) {
        double value = Math.round((s.base() + s.amplitude() * phase) * 10.0) / 10.0;
        rows.add(Telemetry.builder()
            .ts(ts).zone(s.zone()).gatewayId(s.gatewayId())
            .sensorId(s.sensorId()).sensorType(s.type())
            .valueNum(value).unit(s.unit())
            .build());
      }
      if (i % 3 == 0) {
        rows.add(Telemetry.builder()
            .ts(ts).zone("office_1").gatewayId("gw_hcmc_office")
            .sensorId("s_office01_mq2").sensorType("smoke").valueBool(false)
            .build());
        rows.add(Telemetry.builder()
            .ts(ts).zone("meeting").gatewayId("gw_hcmc_office")
            .sensorId("s_meeting_mq2").sensorType("smoke").valueBool(false)
            .build());
      }
    }
    telemetryRepo.saveAll(rows);

    if (sensorLatestRepo.count() == 0) {
      for (Series s : numeric) {
        sensorLatestRepo.save(SensorLatest.builder()
            .sensorId(s.sensorId()).zone(s.zone()).sensorType(s.type())
            .valueNum(s.base()).unit(s.unit()).ts(now)
            .build());
      }
      sensorLatestRepo.save(SensorLatest.builder()
          .sensorId("s_office01_mq2").zone("office_1").sensorType("smoke").valueBool(false).ts(now)
          .build());
      sensorLatestRepo.save(SensorLatest.builder()
          .sensorId("s_meeting_mq2").zone("meeting").sensorType("smoke").valueBool(false).ts(now)
          .build());
    }

    log.info("Seeded {} telemetry rows in {}ms", rows.size(), System.currentTimeMillis() - startMs);
  }

  void seedDeviceHealth() {
    if (deviceHealthRepo.count() > 0) {
      log.debug("Device health already present — skipping health seed");
      return;
    }
    long startMs = System.currentTimeMillis();
    log.info("Seeding local dev device health");

    OffsetDateTime now = Clocks.nowUtc();
    saveHealth("gw_hcmc_office", DeviceHealth.ConnectionStatus.ONLINE, now, 41, 12, -58);
    saveHealth("d_meeting_ahu", DeviceHealth.ConnectionStatus.ONLINE, now.minusSeconds(15), 30, 9, -55);
    saveHealth("d_office01_light", DeviceHealth.ConnectionStatus.OFFLINE, now.minusHours(2), 25, 4, -74);
    saveHealth("d_wd05_curtain", DeviceHealth.ConnectionStatus.OFFLINE, now.minusDays(1), 28, 6, -80);

    log.info("Seeded device health in {}ms", System.currentTimeMillis() - startMs);
  }

  void seedRules() {
    ruleRepo.deleteAll();
    log.info("Cleared all rule engine rules from database to let object simulator control device states");
  }

  void seedCommandsAndDeviceState() {
    if (deviceStateRepo.count() > 0) {
      log.debug("Device states already present — skipping seed");
      return;
    }
    long startMs = System.currentTimeMillis();
    log.info("Seeding local dev default device states");

    OffsetDateTime now = Clocks.nowUtc();

    // Auto-seed states for all control devices in the HCMC Office
    List<Device> allDevices = deviceRepo.findAll();
    for (Device d : allDevices) {
      if (d.getCategory() == Device.Category.device) {
        String id = d.getDeviceId();
        String defaultState = d.getDeviceType().equals("curtain") ? "DOWN" : "OFF";
        Map<String, Object> attrs = d.getDeviceType().equals("ac") ? Map.of("set_temp", 24, "mode", "COOL") : Map.of();
        try {
          deviceStateRepo.upsertDesired(id, defaultState, json.writeValueAsString(attrs), null, now);
          deviceStateRepo.upsertReported(id, defaultState);
        } catch (Exception e) {
          throw new RuntimeException("Failed to seed device state for " + id, e);
        }
      }
    }

    log.info("Seeded default device states in {}ms", System.currentTimeMillis() - startMs);
  }

  void seedAlerts() {
    if (alertRepo.count() > 0) {
      log.debug("Alerts already present — skipping alert seed");
      return;
    }
    long startMs = System.currentTimeMillis();
    log.info("Seeding local dev alerts");

    OffsetDateTime now = Clocks.nowUtc();

    alertRepo.save(Alert.builder()
        .type("TEMP_HIGH").severity(Alert.Severity.WARNING).zone("meeting")
        .sourceDevice(device("s_meeting_dht22"))
        .message("Nhiệt độ phòng họp vượt quá ngưỡng cảnh báo 28°C (Hiện tại: 29.5°C).")
        .status(Alert.Status.ACK)
        .acknowledgedBy("admin").acknowledgedAt(now.minusMinutes(30))
        .build());

    alertRepo.save(Alert.builder()
        .type("DEVICE_OFFLINE").severity(Alert.Severity.INFO).zone("office_1")
        .sourceDevice(device("d_office01_light"))
        .message("Thiết bị Đèn Văn phòng 1 (d_office01_light) mất kết nối mạng và không gửi được heartbeat.")
        .status(Alert.Status.RESOLVED)
        .resolvedBy("admin").resolvedAt(now.minusHours(1))
        .build());

    alertRepo.save(Alert.builder()
        .type("COMMAND_SUPPRESSION_SUSPECTED").severity(Alert.Severity.WARNING).zone("meeting")
        .sourceDevice(device("d_meeting_ahu"))
        .message("Phát hiện nhiều lệnh điều khiển gửi tới d_meeting_ahu bị hết hạn (timeout) liên tiếp")
        .status(Alert.Status.ACK)
        .acknowledgedBy("admin").acknowledgedAt(now.minusMinutes(10))
        .build()); // ACK

    log.info("Seeded alerts in {}ms", System.currentTimeMillis() - startMs);
  }

  private void saveUser(String username, Role role) {
    if (userRepo.findByUsername(username).isPresent()) {
      return;
    }
    userRepo.save(User.builder()
        .username(username)
        .passwordHash(passwordEncoder.encode(PRESET_PASSWORD))
        .role(role)
        .status(User.Status.ACTIVE)
        .build());
  }

  private Device saveGateway(String deviceId, String zone, Device.Status status) {
    return deviceRepo.findById(deviceId).orElseGet(() -> deviceRepo.save(Device.builder()
        .deviceId(deviceId)
        .category(Device.Category.gateway)
        .deviceType("gateway")
        .zone(zone)
        .firmwareVersion("1.4.2")
        .status(status)
        .protocols(new String[]{"mqtt", "http"})
        .build()));
  }

  private void saveSensor(String sensorId, String type, String zone, Device gateway) {
    if (!deviceRepo.existsById(sensorId)) {
      deviceRepo.save(Device.builder()
          .deviceId(sensorId)
          .category(Device.Category.sensor)
          .deviceType(type)
          .zone(zone)
          .parentGateway(gateway)
          .status(Device.Status.ACTIVE)
          .protocols(new String[]{"mqtt"})
          .build());
    }
    if (!sensorRepo.existsById(sensorId)) {
      sensorRepo.save(Sensor.builder()
          .sensorId(sensorId)
          .gateway(gateway)
          .type(type)
          .zone(zone)
          .build());
    }
  }

  private void saveDevice(String deviceId, String type, String zone, Device.Status status) {
    if (deviceRepo.existsById(deviceId)) {
      return;
    }
    deviceRepo.save(Device.builder()
        .deviceId(deviceId)
        .category(Device.Category.device)
        .deviceType(type)
        .zone(zone)
        .firmwareVersion("1.0.0")
        .status(status)
        .protocols(new String[]{"mqtt"})
        .build());
  }

  private void saveHealth(String deviceId, DeviceHealth.ConnectionStatus status,
                          OffsetDateTime lastSeen, int memPct, int cpuPct, int rssi) {
    deviceHealthRepo.upsert(deviceId, status.name(), lastSeen,
        (short) memPct, (short) cpuPct, (short) rssi);
  }

  private Command saveCommand(String commandId, String targetId, String action,
                              Map<String, Object> parameters, Command.Status status,
                              String issuedBy, OffsetDateTime issuedAt) {
    Device target = device(targetId);
    return commandRepo.save(Command.builder()
        .commandId(commandId)
        .target(target)
        .type(target.getDeviceType())
        .action(action)
        .parameters(parameters)
        .status(status)
        .issuedBy(issuedBy)
        .issuedAt(issuedAt)
        .build());
  }

  private void saveDeviceState(String deviceId, String desired, String reported,
                                 Map<String, Object> attributes, Command lastCommand) {
    deviceStateRepo.upsertDesired(deviceId, desired, json.writeValueAsString(attributes),
        lastCommand.getCommandId(), lastCommand.getIssuedAt());
    deviceStateRepo.upsertReported(deviceId, reported);
  }

  private Device device(String deviceId) {
    return deviceRepo.findById(deviceId)
        .orElseThrow(() -> new IllegalStateException("Seed device missing: " + deviceId));
  }
}
