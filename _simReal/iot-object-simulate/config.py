# Configuration for IoT Device & Sensor Simulation System

# Local MQTT Broker shared with Gateway & Backend
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
TOPIC_TELEMETRY = "duk1chvietcong/hcmc_office/telemetry"
TOPIC_COMMAND = "duk1chvietcong/hcmc_office/command"
TOPIC_WEATHER_STATE = "simreal/weather/state"

# AES-CCM Security Configuration (Simulated Link Key derived from Zigbee 3.0 Install Code)
AES_KEY = b"IoT_prj_gr21"

# Zone ID Hex Codes
ZONE_CODES = {
    "pantry": 0x01,
    "storage": 0x02,
    "prvt_meeting": 0x03,
    "office_1": 0x04,
    "office_2": 0x05,
    "lobby": 0x06,
    "connect": 0x07,
    "director": 0x08,
    "finance_mng": 0x09,
    "finace_mng": 0x09,  # Backward compatibility alias
    "meeting": 0x0A,
    "technical_mng": 0x0B,
    "vice_director": 0x0C,
    "balcony": 0x0D,     # Outdoor balcony zone
    
    # Doors
    "door_01": 0xD1,
    "door_02": 0xD2,
    "door_03": 0xD3,
    "door_04": 0xD4,
    "door_05": 0xD5,
    
    # Windows
    "wd_01": 0xE1,
    "wd_02": 0xE2,
    "wd_03": 0xE3,
    "wd_04": 0xE4,
    "wd_05": 0xE5,
    "wd_06": 0xE6
}

# Code to Zone Name mapping
CODE_TO_ZONE = {
    0x01: "pantry",
    0x02: "storage",
    0x03: "prvt_meeting",
    0x04: "office_1",
    0x05: "office_2",
    0x06: "lobby",
    0x07: "connect",
    0x08: "director",
    0x09: "finance_mng",
    0x0A: "meeting",
    0x0B: "technical_mng",
    0x0C: "vice_director",
    0x0D: "balcony",
    0xD1: "door_01",
    0xD2: "door_02",
    0xD3: "door_03",
    0xD4: "door_04",
    0xD5: "door_05",
    0xE1: "wd_01",
    0xE2: "wd_02",
    0xE3: "wd_03",
    0xE4: "wd_04",
    0xE5: "wd_05",
    0xE6: "wd_06"
}

# Type Code mapping for sensors and actuators
TYPE_CODES = {
    # Sensors
    "dht22": 0x11,
    "mq2": 0x12,
    "lm393": 0x13,
    "mc38": 0x14,
    
    # Actuators
    "light": 0x21,
    "ahu": 0x22,
    "curtain": 0x23
}

CODE_TO_TYPE = {code: name for name, code in TYPE_CODES.items()}

# Standard Zones list
ZONES = ["pantry", "storage", "prvt_meeting", "office_1", "office_2", "lobby", 
         "connect", "director", "finance_mng", "meeting", "technical_mng", "vice_director", "balcony"]

# Adjacent relationships mapping for thermal & airflow simulation
DOOR_ADJACENT = {
    "door_01": ("outside", "lobby"),
    "door_02": ("outside", "lobby"),
    "door_03": ("balcony", "director"),
    "door_04": ("balcony", "meeting"),
    "door_05": ("balcony", "vice_director")
}

WINDOW_ADJACENT = {
    "wd_01": ("outside", "lobby"),
    "wd_02": ("outside", "office_1"),
    "wd_03": ("outside", "office_2"),
    "wd_04": ("balcony", "director", "finance_mng"),
    "wd_05": ("balcony", "meeting"),
    "wd_06": ("balcony", "vice_director", "technical_mng")
}

def get_device_creds(zone_name: str, type_name: str) -> dict:
    """Generate simulated MAC address and Install Code per device"""
    zone_code = ZONE_CODES.get(zone_name, 0x00)
    type_code = TYPE_CODES.get(type_name, 0x00)
    mac = f"010000{zone_code:02X}{type_code:02X}"
    install_code = f"INST_{zone_name.upper()}_{type_name.upper()}"
    return {"mac": mac, "install_code": install_code}
