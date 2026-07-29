package com.huylq.iotprojectserver.api.dto.command;

import com.huylq.iotprojectserver.command.DeviceState;

import java.time.OffsetDateTime;
import java.util.Map;
import java.util.Objects;

/**
 * Desired-vs-reported mirror row (OpenAPI {@code DeviceState}, API §6). {@code zone} is
 * resolved from the device registry (not stored on the mirror); {@code inFlight} is
 * server-computed ({@code desiredState != reportedState}) — a command in flight or a
 * drift to investigate.
 */
public record DeviceStateDto(
    String deviceId,
    String zone,
    String desiredState,
    String reportedState,
    boolean inFlight,
    Map<String, Object> attributes,
    String lastCommandId,
    OffsetDateTime commandedAt,
    OffsetDateTime updatedAt) {

  public static DeviceStateDto from(DeviceState d) {
    return new DeviceStateDto(d.getDeviceId(), d.getDevice().getZone(), d.getDesiredState(), d.getReportedState(),
        !Objects.equals(d.getDesiredState(), d.getReportedState()), d.getAttributes(), d.getLastCommandId(),
        d.getCommandedAt(), d.getUpdatedAt());
  }
}
