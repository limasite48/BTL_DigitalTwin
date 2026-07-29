"""
Backend Adapter — bridge between Gateway (AES-CCM decrypted) and Spring Boot Backend.

Gateway maintains AES-CCM security link with sensors. After decryption, gateway uses
this module to translate data into standardized MQTT contracts for the backend:

  - Telemetry:  iot/{gateway_id}/telemetry/{zone}
                {timestamp, zone, gateway_id, sensors:[{id,type,value,unit?}]}
  - Heartbeat:  iot/heartbeat/{device_id}
                {device_id, timestamp, memory_usage_pct, cpu_usage_pct, wifi_rssi}
  - Command:    iot/command/{device_id}     (server -> gateway)
  - Ack:        iot/command_ack/{device_id}  {command_id, device_id, status, executed_at}
"""
import json
import random
from datetime import datetime, timezone

# Standard 13 Zones list
ZONES = ["pantry", "storage", "prvt_meeting", "office_1", "office_2", "lobby", 
         "connect", "director", "finance_mng", "meeting", "technical_mng", "vice_director", "balcony"]

# Backend MQTT Topics
def telemetry_topic(zone, gateway_id):
    return f"iot/{gateway_id}/telemetry/{zone}"

def heartbeat_topic(device_id):
    return f"iot/heartbeat/{device_id}"

def ack_topic(device_id):
    return f"iot/command_ack/{device_id}"

BACKEND_COMMAND_SUB = "iot/command/#"

# Zone emulator to backend gateway_id mapping
ZONE_TO_GATEWAY = {z: "gw_hcmc_office" for z in ZONES}

# Parent zone mappings for door and window objects
OBJECT_PARENT_ZONE = {
    "door_01": "lobby",
    "door_02": "lobby",
    "door_03": "director",
    "door_04": "meeting",
    "door_05": "vice_director",
    "wd_01": "lobby",
    "wd_02": "office_1",
    "wd_03": "office_2",
    "wd_04": "director",
    "wd_05": "meeting",
    "wd_06": "vice_director",
}

# Mapping: (zone, emulator sensor type) -> backend sensor list
SENSOR_MAP = {}
for z in ZONES:
    z_id = "office01" if z == "office_1" else ("office02" if z == "office_2" else z)
    # DHT22 (temp + humid)
    SENSOR_MAP[(z, "dht22")] = [
        (f"s_{z_id}_dht22", "temp", "C", "temp"),
        (f"s_{z_id}_dht22", "hmid", "%", "humid"),
    ]
    # MQ2 (smoke)
    SENSOR_MAP[(z, "mq2")] = [(f"s_{z_id}_mq2", "smoke", None, "smoke")]
    # LM393 (light)
    SENSOR_MAP[(z, "lm393")] = [(f"s_{z_id}_lm393", "light", "lux", "light_intensity")]

# MC38 for Doors and Windows
for i in range(1, 6):
    SENSOR_MAP[(f"door_0{i}", "mc38")] = [(f"s_door0{i}_mc38", "open", None, "status")]
for i in range(1, 7):
    SENSOR_MAP[(f"wd_0{i}", "mc38")] = [(f"s_wd0{i}_mc38", "open", None, "status")]

# Actuators (Indoor 12 Zones, excluding outdoor balcony)
for z in ZONES:
    if z == "balcony":
        continue
    z_id = "office01" if z == "office_1" else ("office02" if z == "office_2" else z)
    # Light actuator status
    SENSOR_MAP[(z, "light")] = [(f"d_{z_id}_light", "light", None, "status")]
    # AHU actuator status
    SENSOR_MAP[(z, "ahu")] = [(f"d_{z_id}_ahu", "ahu", None, "status")]

# Curtain actuator status
for i in range(1, 7):
    SENSOR_MAP[(f"wd_0{i}", "curtain")] = [(f"d_wd0{i}_curtain", "curtain", None, "percentage_cover")]


# Mapping: backend device -> emulator downlink device
BACKEND_DEVICES = {}
for z in ZONES:
    if z == "balcony":
        continue
    z_id = "office01" if z == "office_1" else ("office02" if z == "office_2" else z)
    # Light
    BACKEND_DEVICES[f"d_{z_id}_light"] = {"emu_target": z, "emu_device": "light"}
    # AHU (AC)
    BACKEND_DEVICES[f"d_{z_id}_ahu"] = {"emu_target": z, "emu_device": "ahu"}

# Window curtains (wd_01 to wd_06)
for i in range(1, 7):
    BACKEND_DEVICES[f"d_wd0{i}_curtain"] = {"emu_target": f"wd_0{i}", "emu_device": "curtain"}


# Dynamic Heartbeat Devices list
HEARTBEAT_DEVICES = []
# Single Gateway
HEARTBEAT_DEVICES.append("gw_hcmc_office")

# Sensors
for (z, s_type), sensors in SENSOR_MAP.items():
    for sensor_id, _, _, _ in sensors:
        HEARTBEAT_DEVICES.append(sensor_id)

# Devices
for dev_id in BACKEND_DEVICES.keys():
    HEARTBEAT_DEVICES.append(dev_id)


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_telemetry(zone_name, type_name, decoded):
    """Construct backend telemetry payload from decoded hardware data. Returns (topic, json_str) or None."""
    entries = SENSOR_MAP.get((zone_name, type_name))
    if not entries:
        return None
    parent_zone = OBJECT_PARENT_ZONE.get(zone_name, zone_name)
    gw = ZONE_TO_GATEWAY.get(parent_zone)
    if not gw:
        return None
    sensors = []
    for sensor_id, backend_type, unit, key in entries:
        if key not in decoded:
            continue
        val = decoded[key]
        if backend_type == "open":
            val = (val == "OPEN" or val == "MỞ" or val is True)
        elif type_name in ["light", "ahu"]:
            val = (val == "ON" or val == "BẬT" or val is True)
        item = {"id": sensor_id, "type": backend_type, "value": val}
        if unit:
            item["unit"] = unit
        sensors.append(item)
    if not sensors:
        return None
    payload = {
        "timestamp": _now_iso(),
        "zone": parent_zone,
        "gateway_id": gw,
        "sensors": sensors,
    }
    return telemetry_topic(parent_zone, gw), json.dumps(payload, ensure_ascii=False)


def build_heartbeat(device_id):
    """Construct backend heartbeat payload. Returns (topic, json_str)."""
    payload = {
        "device_id": device_id,
        "timestamp": _now_iso(),
        "status": "ONLINE",
        "memory_usage_pct": random.randint(35, 50),
        "cpu_usage_pct": random.randint(8, 20),
        "wifi_rssi": random.randint(-65, -50),
    }
    return heartbeat_topic(device_id), json.dumps(payload)


def translate_command(device_id, parameters):
    """
    Translate backend command parameters into (emu_target, emu_device, emu_cmd).
    """
    mapping = BACKEND_DEVICES.get(device_id)
    if not mapping or not mapping["emu_device"]:
        return None, None, None
    target = mapping["emu_target"]
    device = mapping["emu_device"]
    params = parameters or {}

    if device == "light":
        active = str(params.get("status", "")).upper() == "ON"
        return target, "light", {"active": active}

    if device == "ahu":
        active = str(params.get("status", "")).upper() == "ON"
        temp_set = params.get("set_temp", 24)
        fan_speed = params.get("fan_speed", 2)
        return target, "ahu", {"active": active, "fan_speed": int(fan_speed), "temp_set": float(temp_set)}

    if device == "curtain":
        direction = str(params.get("direction", "")).upper()
        pct = 100 if direction == "DOWN" else (0 if direction == "UP" else 50)
        return target, "curtain", {"percentage_cover": pct}

    return None, None, None
