import time
import math
import random
from datetime import datetime, timedelta
import hashlib
from config import (
    ZONES, ZONE_CODES, TYPE_CODES, DOOR_ADJACENT, WINDOW_ADJACENT,
    get_device_creds
)
from protocol import (
    encode_dht22, encode_mq2, encode_lm393, encode_mc38,
    encode_light, encode_ahu, encode_curtain
)

class OfficeSimulation:
    def __init__(self):
        # Simulation time state
        self.sim_time = datetime(2026, 7, 1, 8, 0, 0)
        self.time_speed = 1.0 # Time speed multiplier (1.0 = real-time, 60.0 = 1s real is 1m sim)
        self.last_update_real_time = time.time()
        
        # Outdoor environment state (Received from weather-simulate via MQTT IPC topic simreal/weather/state)
        self.outdoor_temp = 36.0
        self.outdoor_humid = 80.0
        self.outdoor_light = 0.0 # lux
        self.outdoor_rain = 0    # 0: dry, 1: rain
        
        # Zone environmental states
        self.zone_states = {}
        for zone in ZONES:
            st = {
                "temp": round(random.uniform(28.0, 34.0), 1),
                "humid": round(random.uniform(50.0, 80.0), 1),
                "smoke": False,
                "light_intensity": 150,
            }
            if zone != "balcony":
                st["light_active"] = False
                st["ahu_active"] = False
                st["ahu_fan_speed"] = 1 # 1: Low, 2: Medium, 3: High
                st["ahu_temp_set"] = 25.0
            self.zone_states[zone] = st
            
        # Door states
        self.doors = {f"door_0{i}": {"is_open": False, "auto_close_time": None} for i in range(1, 6)}
        
        # Window states
        self.windows = {f"wd_0{i}": {"is_open": False, "curtain_pct": 100} for i in range(1, 7)}
        
        # Hex frame publish queues
        self.publish_queue = []
        self.priority_publish_queue = []
        
        # Telemetry and state sync tracking
        self.last_telemetry_real_time = 0.0
        self.last_sync_real_time = 0.0
        
        # Generate initial device states
        self.generate_initial_state()

    def get_device_key(self, zone_name: str, type_name: str) -> bytes:
        """Generate derived Link Key from device Install Code"""
        creds = get_device_creds(zone_name, type_name)
        install_code = creds["install_code"]
        return hashlib.sha256(install_code.encode()).digest()[:16]

    def on_weather_state_received(self, payload: dict):
        """Receive outdoor weather data from IPC Topic simreal/weather/state"""
        try:
            if "atmosphere" in payload:
                atm = payload["atmosphere"]
                self.outdoor_temp = float(atm.get("temperature", self.outdoor_temp))
                self.outdoor_humid = float(atm.get("humidity", self.outdoor_humid))
                self.outdoor_rain = int(atm.get("rain_state", 0))
            if "sun" in payload:
                sun = payload["sun"]
                self.outdoor_light = float(sun.get("solar_irradiance_lux", self.outdoor_light))
        except Exception:
            pass

    def update(self):
        """Physics and environmental logic update loop"""
        now_real = time.time()
        dt_real = now_real - self.last_update_real_time
        self.last_update_real_time = now_real
        
        dt_sim = dt_real * self.time_speed
        self.sim_time += timedelta(seconds=dt_sim)

        # 1. Handle auto-close doors
        for door_id, door_info in self.doors.items():
            if door_info["is_open"] and door_info["auto_close_time"] is not None:
                if self.sim_time >= door_info["auto_close_time"]:
                    self.set_door_state(door_id, False)
                    door_info["auto_close_time"] = None
                    
        # Simulate working hours occupancy (Mon-Fri, 8:00 to 18:00)
        is_working_day = self.sim_time.weekday() < 5
        is_working_hour = 8 <= self.sim_time.hour < 18
        in_office_hours = is_working_day and is_working_hour
        
        if in_office_hours:
            if random.random() < 0.01 * dt_real:
                random_door = f"door_0{random.randint(1, 5)}"
                if not self.doors[random_door]["is_open"]:
                    self.set_door_state(random_door, True)
                    self.doors[random_door]["auto_close_time"] = self.sim_time + timedelta(seconds=random.randint(5, 15))
        
        # 2. Update each Zone state
        for zone in ZONES:
            state = self.zone_states[zone]
            
            # --- Temperature Update ---
            k_conduction = 0.00005 
            k_ventilation = 0.0
            
            for wd_id, adj in WINDOW_ADJACENT.items():
                if zone in adj:
                    if self.windows[wd_id]["is_open"]:
                        k_ventilation += 0.002
                        
            for door_id, adj in DOOR_ADJACENT.items():
                if zone in adj:
                    if self.doors[door_id]["is_open"]:
                        k_ventilation += 0.001
                        
            temp_diff_outdoor = self.outdoor_temp - state["temp"]
            state["temp"] += (k_conduction + k_ventilation) * temp_diff_outdoor * dt_sim
            
            if in_office_hours:
                state["temp"] += 0.00002 * dt_sim
                
            if state.get("ahu_active", False):
                fan_mult = state.get("ahu_fan_speed", 1)
                k_ahu = 0.002 * fan_mult
                state["temp"] += k_ahu * (state.get("ahu_temp_set", 25.0) - state["temp"]) * dt_sim
                
            state["temp"] = round(state["temp"], 4)
            
            # --- Humidity Update ---
            humid_diff_outdoor = self.outdoor_humid - state["humid"]
            state["humid"] += (0.0001 + k_ventilation) * humid_diff_outdoor * dt_sim
            
            if state.get("ahu_active", False) and state.get("ahu_temp_set", 25.0) < state["temp"]:
                state["humid"] += 0.003 * (45.0 - state["humid"]) * dt_sim
                
            state["humid"] = round(max(10.0, min(100.0, state["humid"])), 2)
            
            # --- Illuminance Update ---
            # Differentiate Window Perimeter Zones vs Enclosed Interior Zones
            WINDOW_ZONES = {"office_1", "pantry", "director", "finance_mng", "meeting", "technical_mng", "vice_director", "office_2", "lobby"}
            
            window_light_sum = 0.0
            window_count = 0
            for wd_id, adj in WINDOW_ADJACENT.items():
                if zone in adj:
                    window_count += 1
                    curtain_pct = self.windows[wd_id]["curtain_pct"]
                    transmissivity = 1.0 - (curtain_pct / 100.0) * 0.90
                    window_light_sum += self.outdoor_light * transmissivity * 0.55

            if window_count > 0:
                outdoor_contribution = window_light_sum / window_count
            elif zone in WINDOW_ZONES:
                outdoor_contribution = self.outdoor_light * 0.45
            else:
                # Enclosed interior zones (storage, prvt_meeting, connect) receive only ~3% indirect ambient spill
                outdoor_contribution = self.outdoor_light * 0.03

            lamp_contribution = 350.0 if state.get("light_active", False) else 0.0
            base_light = 5.0
            
            target_light = base_light + outdoor_contribution + lamp_contribution
            state["light_intensity"] = max(0, int(target_light + random.randint(-2, 2)))

            # --- Dedicated Physical Model for Outdoor Balcony ---
            if zone == "balcony":
                rain_cool = 2.5 if getattr(self, 'outdoor_rain', 0) == 1 else 0.0
                target_balcony_temp = max(10.0, self.outdoor_temp - 2.5 - rain_cool)
                state["temp"] += 0.03 * (target_balcony_temp - state["temp"]) * dt_sim
                state["temp"] = round(state["temp"], 2)

                state["humid"] += 0.03 * (self.outdoor_humid - state["humid"]) * dt_sim
                state["humid"] = round(max(10.0, min(100.0, state["humid"])), 2)

                target_balcony_light = max(5.0, self.outdoor_light)
                state["light_intensity"] = max(0, int(target_balcony_light + random.randint(-3, 3)))
            
        # 3. Periodic Sensor Telemetry (every 5 real seconds)
        if now_real - self.last_telemetry_real_time >= 5.0:
            self.last_telemetry_real_time = now_real
            self.generate_sensor_telemetry()
            
        # 4. Periodic Device State Sync (every 60 real seconds)
        if now_real - self.last_sync_real_time >= 60.0:
            self.last_sync_real_time = now_real
            self.generate_device_telemetry()
            
    def get_sensor_reading(self, zone: str, type_name: str) -> str:
        """Fetch current sensor reading and return hex packet"""
        if zone not in self.zone_states:
            return None
        state = self.zone_states[zone]
        zone_code = ZONE_CODES[zone]
        
        key = self.get_device_key(zone, type_name)
        if type_name == "dht22":
            return encode_dht22(zone_code, state["temp"], state["humid"], key)
        elif type_name == "mq2":
            return encode_mq2(zone_code, state["smoke"], key)
        elif type_name == "lm393":
            return encode_lm393(zone_code, state["light_intensity"], key)
        return None
            
    def generate_sensor_telemetry(self):
        """Generate periodic sensor telemetry hex frames"""
        for zone in ZONES:
            state = self.zone_states[zone]
            zone_code = ZONE_CODES[zone]
            
            # DHT22
            key_dht = self.get_device_key(zone, "dht22")
            self.publish_queue.append((
                zone_code, 
                TYPE_CODES["dht22"], 
                encode_dht22(zone_code, state["temp"], state["humid"], key_dht)
            ))
            
            # MQ2
            key_mq2 = self.get_device_key(zone, "mq2")
            self.publish_queue.append((
                zone_code, 
                TYPE_CODES["mq2"], 
                encode_mq2(zone_code, state["smoke"], key_mq2)
            ))
            
            # LM393
            key_lm = self.get_device_key(zone, "lm393")
            self.publish_queue.append((
                zone_code, 
                TYPE_CODES["lm393"], 
                encode_lm393(zone_code, state["light_intensity"], key_lm)
            ))

    def generate_device_telemetry(self):
        """Generate telemetry frames for actuators, doors, and windows"""
        # 1. Lights and AHUs for 12 indoor zones (excluding balcony)
        for zone in ZONES:
            if zone == "balcony":
                continue
            state = self.zone_states[zone]
            zone_code = ZONE_CODES[zone]
            
            # Light
            key_light = self.get_device_key(zone, "light")
            self.publish_queue.append((
                zone_code,
                TYPE_CODES["light"],
                encode_light(zone_code, state.get("light_active", False), key_light)
            ))
            
            # AHU
            key_ahu = self.get_device_key(zone, "ahu")
            self.publish_queue.append((
                zone_code,
                TYPE_CODES["ahu"],
                encode_ahu(zone_code, state.get("ahu_active", False), state.get("ahu_fan_speed", 1), state.get("ahu_temp_set", 25.0), key_ahu)
            ))
            
        # 2. Doors (MC38)
        for door_id in self.doors:
            door_code = ZONE_CODES[door_id]
            is_open = self.doors[door_id]["is_open"]
            key_door = self.get_device_key(door_id, "mc38")
            self.publish_queue.append((
                door_code,
                TYPE_CODES["mc38"],
                encode_mc38(door_code, is_open, key_door)
            ))
            
        # 3. Windows & Curtains (MC38, Curtain)
        for wd_id in self.windows:
            wd_code = ZONE_CODES[wd_id]
            is_open = self.windows[wd_id]["is_open"]
            curtain_pct = self.windows[wd_id]["curtain_pct"]
            
            key_wd_mc38 = self.get_device_key(wd_id, "mc38")
            self.publish_queue.append((
                wd_code,
                TYPE_CODES["mc38"],
                encode_mc38(wd_code, is_open, key_wd_mc38)
            ))
            
            key_curtain = self.get_device_key(wd_id, "curtain")
            self.publish_queue.append((
                wd_code,
                TYPE_CODES["curtain"],
                encode_curtain(wd_code, curtain_pct, key_curtain)
            ))

    def generate_initial_state(self):
        """Generate initial state telemetry for all devices"""
        self.generate_sensor_telemetry()
        self.generate_device_telemetry()

    def set_door_state(self, door_id: str, is_open: bool):
        """Update door state and publish MC38 Hex frame immediately"""
        if door_id in self.doors:
            old_state = self.doors[door_id]["is_open"]
            self.doors[door_id]["is_open"] = is_open
            
            if old_state != is_open:
                code = ZONE_CODES[door_id]
                key = self.get_device_key(door_id, "mc38")
                hex_msg = encode_mc38(code, is_open, key)
                self.priority_publish_queue.append((code, TYPE_CODES["mc38"], hex_msg))
                return True
        return False

    def set_window_state(self, wd_id: str, is_open: bool):
        """Update window state and publish MC38 Hex frame immediately"""
        if wd_id in self.windows:
            old_state = self.windows[wd_id]["is_open"]
            self.windows[wd_id]["is_open"] = is_open
            
            if old_state != is_open:
                code = ZONE_CODES[wd_id]
                key = self.get_device_key(wd_id, "mc38")
                hex_msg = encode_mc38(code, is_open, key)
                self.priority_publish_queue.append((code, TYPE_CODES["mc38"], hex_msg))
                return True
        return False

    def set_light_state(self, zone: str, active: bool):
        """Update Light state and publish Hex frame immediately"""
        if zone == "balcony":
            return False
        if zone in self.zone_states:
            self.zone_states[zone]["light_active"] = active
            code = ZONE_CODES[zone]
            key = self.get_device_key(zone, "light")
            hex_msg = encode_light(code, active, key)
            self.priority_publish_queue.append((code, TYPE_CODES["light"], hex_msg))
            
            lamp_contrib = 350.0 if active else 0.0
            self.zone_states[zone]["light_intensity"] = max(0, int(5.0 + lamp_contrib))
            return True
        return False

    def set_ahu_state(self, zone: str, active: bool, fan_speed: int = None, temp_set: float = None):
        """Update AHU state and publish Hex frame immediately"""
        if zone == "balcony":
            return False
        if zone in self.zone_states:
            state = self.zone_states[zone]
            state["ahu_active"] = active
            if fan_speed is not None:
                state["ahu_fan_speed"] = int(fan_speed)
            if temp_set is not None:
                state["ahu_temp_set"] = float(temp_set)
                
            code = ZONE_CODES[zone]
            key = self.get_device_key(zone, "ahu")
            hex_msg = encode_ahu(code, state["ahu_active"], state["ahu_fan_speed"], state["ahu_temp_set"], key)
            self.priority_publish_queue.append((code, TYPE_CODES["ahu"], hex_msg))
            return True
        return False

    def set_curtain_state(self, wd_id: str, percentage_cover: int):
        """Update curtain state and publish Hex frame immediately"""
        if wd_id in self.windows:
            percentage_cover = max(0, min(100, int(percentage_cover)))
            self.windows[wd_id]["curtain_pct"] = percentage_cover
            
            code = ZONE_CODES[wd_id]
            key = self.get_device_key(wd_id, "curtain")
            hex_msg = encode_curtain(code, percentage_cover, key)
            self.priority_publish_queue.append((code, TYPE_CODES["curtain"], hex_msg))
            return True
        return False

    def set_smoke_alarm(self, zone: str, has_smoke: bool):
        """Toggle MQ2 smoke alarm in Zone and publish Hex frame immediately"""
        if zone in self.zone_states:
            self.zone_states[zone]["smoke"] = has_smoke
            code = ZONE_CODES[zone]
            key = self.get_device_key(zone, "mq2")
            hex_msg = encode_mq2(code, has_smoke, key)
            self.priority_publish_queue.append((code, TYPE_CODES["mq2"], hex_msg))
            return True
        return False
