package com.huylq.iotprojectserver.command;

import java.util.Set;

/**
 * Shared state-direction helper — both the role×device-class authorization gate
 * ({@link CommandServiceImpl}) and the safety interlock ({@link AlertBasedSafetyInterlockCheck})
 * need to know whether a desired state is moving a safety device *away* from the safe
 * state ("de-escalating") or toward/within it.
 */
final class DeviceStates {

  private static final Set<String> DE_ESCALATING_STATES = Set.of("OFF", "STOP", "CLOSED");

  private DeviceStates() {
  }

  static boolean isDeEscalating(String desiredState) {
    return desiredState != null && DE_ESCALATING_STATES.contains(desiredState.toUpperCase());
  }
}
