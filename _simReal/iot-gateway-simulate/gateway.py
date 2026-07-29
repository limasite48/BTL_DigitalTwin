import time
import json
import os
from datetime import datetime
from config import (
    ZONES, ZONE_CODES, TYPE_CODES, CODE_TO_ZONE, CODE_TO_TYPE,
    TEMP_THRESHOLD, HUMID_THRESHOLD, LIGHT_THRESHOLD,
    TOPIC_SERVER_SEND
)

class GatewayEngine:
    def __init__(self):
        # Server connection status
        self.network_connected = True
        
        # Packet statistics
        self.stats = {
            "rx_zigbee": 0,
            "tx_zigbee": 0,
            "tx_server": 0,
            "filtered": 0,
            "offline_saved": 0
        }
        
        # Device Shadow state document
        self.state_document = {
            "timestamp": None,
            "system_status": "NORMAL",
            "zones": {},
            "doors": {},
            "windows": {}
        }
        
        # Initialize default device shadow state for all zones
        for zone in ZONES:
            st = {
                "temp": 25.0,
                "humid": 60.0,
                "smoke": False,
                "light_intensity": 50
            }
            if zone != "balcony":
                st["light"] = {"status": "OFF"}
                st["ahu"] = {
                    "status": "OFF",
                    "fan_speed": 1,
                    "temp_set": 25.0
                }
            self.state_document["zones"][zone] = st
            
        # Initialize default state for doors (CLOSED)
        for i in range(1, 6):
            self.state_document["doors"][f"door_0{i}"] = {
                "status": "CLOSED"
            }
            
        # Initialize default state for windows & curtains (CLOSED, 100% cover)
        for i in range(1, 7):
            self.state_document["windows"][f"wd_0{i}"] = {
                "status": "CLOSED",
                "curtain": {
                    "status": "CLOSED",
                    "percentage_cover": 100
                }
            }
            
        # Store last sent values per zone for threshold filtering
        self.last_sent_values = {}
        # Store last sent timestamp per zone for heartbeat timeout
        self.last_sent_time = {}
        for zone in ZONES:
            self.last_sent_values[zone] = {
                "temp": None,
                "humid": None,
                "light_intensity": None,
                "smoke": None
            }
            self.last_sent_time[zone] = {
                "temp": 0.0,
                "humid": 0.0,
                "light_intensity": 0.0,
                "smoke": 0.0
            }
            
        # Server publish queue
        self.server_publish_queue = []
        
        # Flag indicating pending telemetry publish to server
        self.pending_publish = False
        
        # Pending delta buffer
        self.pending_delta = {
            "timestamp": None,
            "zones": {},
            "doors": {},
            "windows": {}
        }
        
        # Offline log storage file path
        self.offline_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "offline_telemetry.json")
        
        # Load paired devices configuration
        self.load_paired_devices()

    def get_delta_payload(self) -> dict:
        """Returns delta payload containing modified fields and resets delta buffer"""
        payload = {
            "timestamp": self.pending_delta["timestamp"] or int(time.time()),
            "system_status": "NORMAL"
        }
        
        for section in ["zones", "doors", "windows"]:
            if self.pending_delta[section]:
                payload[section] = self.pending_delta[section]
                
        self.pending_delta = {
            "timestamp": None,
            "zones": {},
            "doors": {},
            "windows": {}
        }
        return payload

    def process_device_update(self, zone_id: int, type_code: int, decoded_data: dict) -> bool:
        """Process update received from Zigbee device, update Device Shadow, and apply edge filter"""
        self.stats["rx_zigbee"] += 1
        
        zone_name = CODE_TO_ZONE.get(zone_id)
        type_name = CODE_TO_TYPE.get(type_code)
        
        if not zone_name or not type_name:
            return False
            
        self.state_document["timestamp"] = int(time.time())
        
        should_publish = False
        is_smoke_alert = False
        
        if zone_name in ZONES:
            zone_data = self.state_document["zones"][zone_name]
            last_sent = self.last_sent_values[zone_name]
            
            current_time = time.time()
            if type_name == "dht22":
                temp = decoded_data["temp"]
                humid = decoded_data["humid"]
                zone_data["temp"] = temp
                zone_data["humid"] = humid
                
                last_t = self.last_sent_time[zone_name]["temp"]
                is_temp_timeout = (current_time - last_t >= 300.0)
                
                if last_sent["temp"] is None or abs(temp - last_sent["temp"]) >= TEMP_THRESHOLD or is_temp_timeout:
                    should_publish = True
                    last_sent["temp"] = temp
                    self.last_sent_time[zone_name]["temp"] = current_time
                    if zone_name not in self.pending_delta["zones"]:
                        self.pending_delta["zones"][zone_name] = {}
                    self.pending_delta["zones"][zone_name]["temp"] = temp
                    
                last_h = self.last_sent_time[zone_name]["humid"]
                is_humid_timeout = (current_time - last_h >= 300.0)
                
                if last_sent["humid"] is None or abs(humid - last_sent["humid"]) >= HUMID_THRESHOLD or is_humid_timeout:
                    should_publish = True
                    last_sent["humid"] = humid
                    self.last_sent_time[zone_name]["humid"] = current_time
                    if zone_name not in self.pending_delta["zones"]:
                        self.pending_delta["zones"][zone_name] = {}
                    self.pending_delta["zones"][zone_name]["humid"] = humid
                    
                if not should_publish:
                    self.stats["filtered"] += 1
                    
            elif type_name == "lm393":
                light = decoded_data["light_intensity"]
                zone_data["light_intensity"] = light
                
                last_l = self.last_sent_time[zone_name]["light_intensity"]
                is_light_timeout = (current_time - last_l >= 300.0)
                
                if last_sent["light_intensity"] is None or abs(light - last_sent["light_intensity"]) >= LIGHT_THRESHOLD or is_light_timeout:
                    should_publish = True
                    last_sent["light_intensity"] = light
                    self.last_sent_time[zone_name]["light_intensity"] = current_time
                    if zone_name not in self.pending_delta["zones"]:
                        self.pending_delta["zones"][zone_name] = {}
                    self.pending_delta["zones"][zone_name]["light_intensity"] = light
                else:
                    self.stats["filtered"] += 1
                    
            elif type_name == "mq2":
                smoke = decoded_data["smoke"]
                zone_data["smoke"] = smoke
                
                last_s = self.last_sent_time[zone_name]["smoke"]
                is_smoke_timeout = (current_time - last_s >= 300.0)
                
                if last_sent["smoke"] != smoke or is_smoke_timeout:
                    should_publish = True
                    if last_sent["smoke"] != smoke and smoke:
                        is_smoke_alert = True
                    last_sent["smoke"] = smoke
                    self.last_sent_time[zone_name]["smoke"] = current_time
                    if zone_name not in self.pending_delta["zones"]:
                        self.pending_delta["zones"][zone_name] = {}
                    self.pending_delta["zones"][zone_name]["smoke"] = smoke
                else:
                    self.stats["filtered"] += 1
                    
            elif type_name == "light":
                zone_data["light"] = decoded_data
                should_publish = True
                if zone_name not in self.pending_delta["zones"]:
                    self.pending_delta["zones"][zone_name] = {}
                self.pending_delta["zones"][zone_name]["light"] = decoded_data
                
            elif type_name == "ahu":
                zone_data["ahu"] = decoded_data
                should_publish = True
                if zone_name not in self.pending_delta["zones"]:
                    self.pending_delta["zones"][zone_name] = {}
                self.pending_delta["zones"][zone_name]["ahu"] = decoded_data
                
        elif zone_name.startswith("door_"):
            self.state_document["doors"][zone_name] = decoded_data
            should_publish = True
            self.pending_delta["doors"][zone_name] = decoded_data
            
        elif zone_name.startswith("wd_"):
            win_data = self.state_document["windows"][zone_name]
            
            if type_name == "mc38":
                win_data["status"] = decoded_data["status"]
                should_publish = True
                if zone_name not in self.pending_delta["windows"]:
                    self.pending_delta["windows"][zone_name] = {}
                self.pending_delta["windows"][zone_name]["status"] = decoded_data["status"]
            elif type_name == "curtain":
                win_data["curtain"] = decoded_data
                should_publish = True
                if zone_name not in self.pending_delta["windows"]:
                    self.pending_delta["windows"][zone_name] = {}
                self.pending_delta["windows"][zone_name]["curtain"] = decoded_data
 
        if should_publish:
            self.pending_delta["timestamp"] = self.state_document["timestamp"]
            
            if is_smoke_alert:
                delta_payload = self.get_delta_payload()
                payload = json.dumps(delta_payload, ensure_ascii=False)
                if self.network_connected:
                    for _ in range(3):
                        self.server_publish_queue.append((TOPIC_SERVER_SEND, payload))
                        self.stats["tx_server"] += 1
                else:
                    self.save_offline_data(delta_payload)
            else:
                self.pending_publish = True
                
            return True
            
        return False

    def save_offline_data(self, data: dict):
        """Save offline data to local JSON file"""
        self.stats["offline_saved"] += 1
        
        existing_logs = []
        if os.path.exists(self.offline_file_path):
            try:
                with open(self.offline_file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        existing_logs = json.loads(content)
            except Exception:
                existing_logs = []
                
        existing_logs.append(data)
        
        try:
            with open(self.offline_file_path, "w", encoding="utf-8") as f:
                json.dump(existing_logs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ERROR] Failed to save offline data file: {e}")

    def sync_offline_data(self):
        """Send all stored offline telemetry data to Server upon reconnecting"""
        if not os.path.exists(self.offline_file_path):
            return 0
            
        count = 0
        try:
            with open(self.offline_file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    offline_records = json.loads(content)
                    for record in offline_records:
                        payload = json.dumps(record, ensure_ascii=False)
                        self.server_publish_queue.append((TOPIC_SERVER_SEND, payload))
                        self.stats["tx_server"] += 1
                        count += 1
                        
            os.remove(self.offline_file_path)
            print(f"\n[OFFLINE] Successfully flushed {count} offline records to server.")
        except Exception as e:
            print(f"[ERROR] Offline sync error: {e}")
            
        return count

    def load_paired_devices(self):
        self.paired_devices = {}
        self.paired_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paired_devices.json")
        if os.path.exists(self.paired_file_path):
            try:
                with open(self.paired_file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        self.paired_devices = json.loads(content)
            except Exception as e:
                print(f"[ERROR] Failed to read paired_devices.json: {e}")
                
        import hashlib
        from config import ZONES, get_device_creds
        
        missing_added = False
        
        # 1. Standard Zones x devices (12 indoor zones have 5 devices, balcony has 3 sensors)
        for zone in ZONES:
            devs = ["dht22", "mq2", "lm393"] if zone == "balcony" else ["dht22", "mq2", "lm393", "light", "ahu"]
            for dev in devs:
                creds = get_device_creds(zone, dev)
                mac = creds["mac"]
                if mac not in self.paired_devices:
                    install_code = creds["install_code"]
                    derived_key = hashlib.sha256(install_code.encode()).digest()[:16]
                    self.paired_devices[mac] = {
                        "zone": zone,
                        "device": dev,
                        "install_code": install_code,
                        "key_hex": derived_key.hex()
                    }
                    missing_added = True
                    
        # 2. Doors (door_01 -> door_05, type: mc38)
        for i in range(1, 6):
            door_id = f"door_0{i}"
            creds = get_device_creds(door_id, "mc38")
            mac = creds["mac"]
            if mac not in self.paired_devices:
                install_code = creds["install_code"]
                derived_key = hashlib.sha256(install_code.encode()).digest()[:16]
                self.paired_devices[mac] = {
                    "zone": door_id,
                    "device": "mc38",
                    "install_code": install_code,
                    "key_hex": derived_key.hex()
                }
                missing_added = True
                
        # 3. Windows (wd_01 -> wd_06, types: mc38, curtain)
        for i in range(1, 7):
            wd_id = f"wd_0{i}"
            for dev in ["mc38", "curtain"]:
                creds = get_device_creds(wd_id, dev)
                mac = creds["mac"]
                if mac not in self.paired_devices:
                    install_code = creds["install_code"]
                    derived_key = hashlib.sha256(install_code.encode()).digest()[:16]
                    self.paired_devices[mac] = {
                        "zone": wd_id,
                        "device": dev,
                        "install_code": install_code,
                        "key_hex": derived_key.hex()
                    }
                    missing_added = True
        
        if missing_added:
            self.save_paired_devices()
            print(f"[Gateway Engine] Auto-paired {len(self.paired_devices)} total devices successfully.", flush=True)

    def unpair_device(self, arg: str) -> tuple[str, str, str]:
        """Unpair device by MAC address or zone/type tuple"""
        arg = arg.strip()
        
        mac_clean = arg.upper().replace(":", "")
        if mac_clean in self.paired_devices:
            info = self.paired_devices.pop(mac_clean)
            self.save_paired_devices()
            return info["zone"], info["device"], None
            
        parts = arg.split()
        if len(parts) == 2:
            zone_name = parts[0].lower()
            type_name = parts[1].lower()
            for mac, info in list(self.paired_devices.items()):
                if info["zone"] == zone_name and info["device"] == type_name:
                    self.paired_devices.pop(mac)
                    self.save_paired_devices()
                    return zone_name, type_name, None
                    
        return None, None, f"No paired device found matching '{arg}'"
                
    def save_paired_devices(self):
        try:
            with open(self.paired_file_path, "w", encoding="utf-8") as f:
                json.dump(self.paired_devices, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ERROR] Failed to save paired_devices.json: {e}")

    def pair_device(self, mac: str, install_code: str) -> tuple[str, str, str]:
        mac = mac.strip().upper().replace(":", "")
        if len(mac) != 10 or not mac.startswith("010000"):
            return None, None, "Invalid simulated MAC format (must be 10 Hex characters starting with 010000)"
        
        try:
            zone_code = int(mac[6:8], 16)
            type_code = int(mac[8:10], 16)
        except ValueError:
            return None, None, "MAC Address contains invalid hex characters"
            
        zone_name = CODE_TO_ZONE.get(zone_code)
        type_name = CODE_TO_TYPE.get(type_code)
        
        if not zone_name or not type_name:
            return None, None, f"Unknown Zone/Type for MAC (Zone Code: 0x{zone_code:02X}, Type Code: 0x{type_code:02X})"
            
        import hashlib
        derived_key = hashlib.sha256(install_code.encode()).digest()[:16]
        
        self.paired_devices[mac] = {
            "zone": zone_name,
            "device": type_name,
            "install_code": install_code,
            "key_hex": derived_key.hex()
        }
        
        self.save_paired_devices()
        return zone_name, type_name, None

    def is_paired(self, zone_name: str, type_name: str) -> bool:
        for mac, info in self.paired_devices.items():
            if info["zone"] == zone_name and info["device"] == type_name:
                return True
        return False
        
    def get_device_key(self, zone_name: str, type_name: str) -> bytes:
        for mac, info in self.paired_devices.items():
            if info["zone"] == zone_name and info["device"] == type_name:
                return bytes.fromhex(info["key_hex"])
        return None
