import os
import sys
import json
import time
import threading
import struct
import hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler
import paho.mqtt.client as mqtt
try:
    from Crypto.Cipher import AES
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

# Configure UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
HTTP_PORT = 8090

# Hardware Constants for AES-CCM Downlink Encryption
ZONE_CODES = {
    "pantry": 0x01, "storage": 0x02, "prvt_meeting": 0x03, "office_1": 0x04,
    "office_2": 0x05, "lobby": 0x06, "connect": 0x07, "director": 0x08,
    "finance_mng": 0x09, "meeting": 0x0A, "technical_mng": 0x0B,
    "vice_director": 0x0C, "balcony": 0x0D,
    "door_01": 0xD1, "door_02": 0xD2, "door_03": 0xD3, "door_04": 0xD4, "door_05": 0xD5,
    "wd_01": 0xE1, "wd_02": 0xE2, "wd_03": 0xE3, "wd_04": 0xE4, "wd_05": 0xE5, "wd_06": 0xE6
}

TYPE_CODES = {
    "dht22": 0x11, "mq2": 0x12, "lm393": 0x13, "mc38": 0x14,
    "light": 0x21, "ahu": 0x22, "curtain": 0x23
}

tx_sequence_counter = 0
tx_lock = threading.Lock()

def get_next_sequence_number() -> int:
    global tx_sequence_counter
    with tx_lock:
        tx_sequence_counter += 1
        return tx_sequence_counter

def get_device_key(target_name: str, type_name: str) -> bytes:
    install_code = f"INST_{target_name.upper()}_{type_name.upper()}"
    return hashlib.sha256(install_code.encode()).digest()[:16]

def wrap_downlink_frame(target_name: str, type_name: str, payload_bytes: bytes) -> str:
    if not HAS_CRYPTO:
        return ""
    zone_id = ZONE_CODES.get(target_name, 0x00)
    type_code = TYPE_CODES.get(type_name, 0x00)
    key = get_device_key(target_name, type_name)

    seq_num = get_next_sequence_number()
    nonce = struct.pack(">BBI", zone_id, type_code, seq_num) + b"\x00" * 7
    cipher = AES.new(key, AES.MODE_CCM, nonce=nonce, mac_len=4)
    ciphertext, tag = cipher.encrypt_and_digest(payload_bytes)

    secure_payload = struct.pack(">I", seq_num) + ciphertext + tag
    length = len(secure_payload)

    chk = zone_id ^ type_code ^ length
    for b in secure_payload:
        chk ^= b

    frame = bytearray([0x5A, zone_id, type_code, length]) + secure_payload + bytearray([chk, 0xA5])
    return frame.hex().upper()


# Global Twin State
state_lock = threading.Lock()
twin_state = {
    "weather": {
        "sim_time": "2026-07-01 08:00:00",
        "elevation": 35.0,
        "azimuth": 104.0,
        "lux": 45000.0,
        "temp": 35.0,
        "humid": 75.0,
        "rain_state": 0,
        "rain_mmh": 0.0,
        "speed": 1.0
    },
    "gateway": {
        "network_connected": True,
        "paired_count": 80,
        "rx_count": 0,
        "tx_count": 0,
        "filt_count": 0
    },
    "zones": {},
    "doors": {},
    "windows": {}
}

# Initialize 13 Zones (12 office + balcony)
ZONES = [
    "pantry", "storage", "prvt_meeting", "office_1", "office_2", "lobby",
    "connect", "director", "finance_mng", "meeting", "technical_mng", "vice_director", "balcony"
]
for z in ZONES:
    st = {
        "temp": 25.0,
        "humid": 60.0,
        "lux": 50,
        "smoke": False
    }
    if z != "balcony":
        st["light"] = "OFF"
        st["ahu"] = {"status": "OFF", "fan_speed": 1, "temp_set": 25.0}
    twin_state["zones"][z] = st

for i in range(1, 6):
    twin_state["doors"][f"door_0{i}"] = {"status": "CLOSED"}

for i in range(1, 7):
    twin_state["windows"][f"wd_0{i}"] = {"status": "CLOSED", "curtain_pct": 100}

# MQTT Client for Web Dashboard
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="simreal_web_dashboard")

def on_mqtt_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        client.subscribe("simreal/weather/state")
        client.subscribe("iot/gw_hcmc_office/telemetry/#")
        client.subscribe("duk1chvietcong/hcmc_office/telemetry")

def on_mqtt_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8', errors='ignore'))
        topic = msg.topic

        with state_lock:
            if topic == "simreal/weather/state":
                sun = payload.get("sun", {})
                atm = payload.get("atmosphere", {})
                w = twin_state["weather"]
                w["sim_time"] = payload.get("sim_time", "N/A").replace("T", " ").replace("Z", "")
                w["speed"] = float(payload.get("speed", 1.0))
                w["elevation"] = sun.get("elevation", 0.0)
                w["azimuth"] = sun.get("azimuth", 0.0)
                w["lux"] = sun.get("solar_irradiance_lux", 0.0)
                w["temp"] = atm.get("temperature", 0.0)
                w["humid"] = atm.get("humidity", 0.0)
                w["rain_state"] = atm.get("rain_state", 0)
                w["rain_mmh"] = atm.get("rain_intensity_mmh", 0.0)
                w["rain_intensity_mmh"] = atm.get("rain_intensity_mmh", 0.0)
                w["cloud_cover_pct"] = atm.get("cloud_cover_pct", 15.0)
                w["weather_mode"] = atm.get("weather_mode", "clear")

            elif "telemetry" in topic:
                twin_state["gateway"]["rx_count"] += 1
                zone_name = payload.get("zone")
                if zone_name in twin_state["zones"]:
                    z_data = twin_state["zones"][zone_name]
                    for s in payload.get("sensors", []):
                        stype = s.get("type")
                        val = s.get("value")
                        if stype == "temp":
                            z_data["temp"] = float(val)
                        elif stype == "hmid":
                            z_data["humid"] = float(val)
                        elif stype == "light":
                            if isinstance(val, bool):
                                if zone_name != "balcony":
                                    z_data["light"] = "ON" if val else "OFF"
                            elif isinstance(val, (int, float)):
                                z_data["lux"] = int(val)
                            elif zone_name != "balcony":
                                is_on = (str(val).upper() in ["ON", "BẬT", "TRUE"])
                                z_data["light"] = "ON" if is_on else "OFF"
                        elif stype == "smoke":
                            z_data["smoke"] = bool(val)
                        elif stype == "ahu" and zone_name != "balcony":
                            if "ahu" not in z_data:
                                z_data["ahu"] = {"status": "OFF", "fan_speed": 1, "temp_set": 25.0}
                            is_on = (val is True or val == "ON" or val == "BẬT")
                            z_data["ahu"]["status"] = "ON" if is_on else "OFF"
                        elif stype == "open":
                            sid = s.get("id", "")
                            if sid.startswith("s_door"):
                                d_num = sid.replace("s_door", "").replace("_mc38", "")
                                d_id = f"door_{d_num}"
                                if d_id in twin_state["doors"]:
                                    twin_state["doors"][d_id]["status"] = "OPEN" if val else "CLOSED"
                            elif sid.startswith("s_wd"):
                                w_num = sid.replace("s_wd", "").replace("_mc38", "")
                                w_id = f"wd_{w_num}"
                                if w_id in twin_state["windows"]:
                                    twin_state["windows"][w_id]["status"] = "OPEN" if val else "CLOSED"
                        elif stype == "curtain":
                            sid = s.get("id", "")
                            if sid.startswith("d_wd"):
                                w_num = sid.replace("d_wd", "").replace("_curtain", "")
                                w_id = f"wd_{w_num}"
                                if w_id in twin_state["windows"]:
                                    twin_state["windows"][w_id]["curtain_pct"] = int(val)
    except Exception:
        pass

mqtt_client.on_connect = on_mqtt_connect
mqtt_client.on_message = on_mqtt_message

class DashboardRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress HTTP access logging in console

    def do_GET(self):
        root_dir = os.path.dirname(os.path.abspath(__file__))
        if self.path == "/" or self.path == "/index.html":
            file_path = os.path.join(root_dir, "index.html")
            self._serve_file(file_path, "text/html; charset=utf-8")
        elif self.path == "/style.css":
            file_path = os.path.join(root_dir, "style.css")
            self._serve_file(file_path, "text/css; charset=utf-8")
        elif self.path == "/app.js":
            file_path = os.path.join(root_dir, "app.js")
            self._serve_file(file_path, "application/javascript; charset=utf-8")
        elif self.path == "/api/state":
            with state_lock:
                data = json.dumps(twin_state, ensure_ascii=False)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data.encode("utf-8"))
        else:
            self.send_error(404, "File Not Found")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/cmd":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(body)
                domain = data.get("domain")

                if domain == "weather":
                    cmd = data.get("command")
                    val = data.get("value")
                    payload = json.dumps({"command": cmd, "value": val})
                    mqtt_client.publish("simreal/weather/cmd", payload)

                elif domain == "gateway":
                    cmd = data.get("command")
                    state = data.get("state")
                    payload = json.dumps({"command": cmd, "state": state})
                    mqtt_client.publish("duk1chvietcong/hcmc_office/gw_cmd", payload)
                    if cmd == "network":
                        with state_lock:
                            twin_state["gateway"]["network_connected"] = (state == "on")

                elif domain == "object":
                    cmd = data.get("command")
                    zone = data.get("zone")

                    # Reject light and ahu operations on balcony
                    if zone == "balcony" and cmd in ["light", "ahu"]:
                        self._send_json_response({"status": "ERROR", "message": "Balcony does not support light/ahu actuators"})
                        return

                    if cmd == "light":
                        active = data.get("active", False)
                        raw = struct.pack(">B", 1 if active else 0)
                        hex_cmd = wrap_downlink_frame(zone, "light", raw)
                        mqtt_client.publish("duk1chvietcong/hcmc_office/command", hex_cmd)
                        with state_lock:
                            if zone in twin_state["zones"]:
                                twin_state["zones"][zone]["light"] = "ON" if active else "OFF"

                    elif cmd == "ahu":
                        active = data.get("active", False)
                        spd = int(data.get("fan_speed", 1))
                        tset = float(data.get("temp_set", 25.0))
                        raw = struct.pack(">BBh", 1 if active else 0, spd, int(tset * 10))
                        hex_cmd = wrap_downlink_frame(zone, "ahu", raw)
                        mqtt_client.publish("duk1chvietcong/hcmc_office/command", hex_cmd)
                        with state_lock:
                            if zone in twin_state["zones"]:
                                twin_state["zones"][zone]["ahu"] = {
                                    "status": "ON" if active else "OFF",
                                    "fan_speed": spd,
                                    "temp_set": tset
                                }

                    elif cmd == "door":
                        door_id = data.get("door_id")
                        is_open = data.get("is_open", False)
                        raw = struct.pack(">B", 1 if is_open else 0)
                        hex_cmd = wrap_downlink_frame(door_id, "mc38", raw)
                        mqtt_client.publish("duk1chvietcong/hcmc_office/command", hex_cmd)
                        with state_lock:
                            if door_id in twin_state["doors"]:
                                twin_state["doors"][door_id]["status"] = "OPEN" if is_open else "CLOSED"

                    elif cmd == "window":
                        wd_id = data.get("wd_id")
                        is_open = data.get("is_open", False)
                        raw = struct.pack(">B", 1 if is_open else 0)
                        hex_cmd = wrap_downlink_frame(wd_id, "mc38", raw)
                        mqtt_client.publish("duk1chvietcong/hcmc_office/command", hex_cmd)
                        with state_lock:
                            if wd_id in twin_state["windows"]:
                                twin_state["windows"][wd_id]["status"] = "OPEN" if is_open else "CLOSED"

                    elif cmd == "curtain":
                        wd_id = data.get("wd_id")
                        pct = int(data.get("pct", 100))
                        raw = struct.pack(">B", pct)
                        hex_cmd = wrap_downlink_frame(wd_id, "curtain", raw)
                        mqtt_client.publish("duk1chvietcong/hcmc_office/command", hex_cmd)
                        with state_lock:
                            if wd_id in twin_state["windows"]:
                                twin_state["windows"][wd_id]["curtain_pct"] = pct

                self._send_json_response({"status": "OK"})
            except Exception as e:
                self.send_error(400, f"Bad Request: {e}")
        else:
            self.send_error(404, "Not Found")

    def _send_json_response(self, data_dict):
        res_data = json.dumps(data_dict, ensure_ascii=False)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(res_data.encode("utf-8"))

    def _serve_file(self, path, mime_type):
        try:
            with open(path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self.send_error(404, "File Not Found")

def main():
    try:
        mqtt_client.connect_async(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
    except Exception as e:
        print(f"[WARN] MQTT Connect Warning: {e}")

    server_address = ("", HTTP_PORT)
    httpd = HTTPServer(server_address, DashboardRequestHandler)
    print(f"=========================================================")
    print(f" SimReal Web Control Dashboard running at:")
    print(f" -> http://localhost:{HTTP_PORT}")
    print(f"=========================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        mqtt_client.loop_stop()

if __name__ == "__main__":
    main()
