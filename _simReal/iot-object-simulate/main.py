import sys
import os
import time
import threading
import json
from datetime import datetime
import paho.mqtt.client as mqtt

# Ensure UTF-8 stdout/stdin encoding for cross-platform compatibility
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stdin, 'reconfigure'):
    sys.stdin.reconfigure(encoding='utf-8')
os.system('')  # Enable VT100 ANSI sequences in Windows CMD

# Add module path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from config import (
    MQTT_BROKER, MQTT_PORT, TOPIC_TELEMETRY, TOPIC_COMMAND, TOPIC_WEATHER_STATE,
    ZONES, ZONE_CODES, TYPE_CODES, CODE_TO_ZONE, CODE_TO_TYPE,
    get_device_creds
)
from protocol import parse_downlink_frame, decode_command_payload
from simulation import OfficeSimulation

# Initialize simulation manager
sim = OfficeSimulation()
log_hex = False
connected_event = threading.Event()

def on_connect(client, userdata, flags, rc, properties=None):
    """Callback when connected to MQTT Broker"""
    client.subscribe(TOPIC_COMMAND)
    client.subscribe(TOPIC_WEATHER_STATE)
    connected_event.set()

def on_message(client, userdata, msg):
    """Callback for incoming MQTT messages"""
    global log_hex
    payload_str = msg.payload.decode("utf-8", errors="ignore").strip()

    # Weather state IPC payload
    if msg.topic == TOPIC_WEATHER_STATE:
        try:
            weather_payload = json.loads(payload_str)
            sim.on_weather_state_received(weather_payload)
        except Exception:
            pass
        return

    # Downlink command payload
    try:
        hex_clean = payload_str.strip().replace(" ", "")
        data_bytes = bytes.fromhex(hex_clean)
        if len(data_bytes) >= 4:
            zone_id = data_bytes[1]
            type_code = data_bytes[2]
            zone_name = CODE_TO_ZONE.get(zone_id)
            type_name = CODE_TO_TYPE.get(type_code)
            key = sim.get_device_key(zone_name, type_name) if zone_name and type_name else None
        else:
            key = None
    except Exception:
        key = None

    parsed = parse_downlink_frame(payload_str, key)
    if not parsed:
        return

    zone_code = parsed["zone_id"]
    type_code = parsed["type_code"]
    payload_bytes = parsed["payload"]

    zone_name = CODE_TO_ZONE.get(zone_code)
    type_name = CODE_TO_TYPE.get(type_code)

    if not zone_name or not type_name:
        return

    cmd_data = decode_command_payload(type_code, payload_bytes)
    if not cmd_data:
        return

    if type_name == "light":
        sim.set_light_state(zone_name, cmd_data["active"])
    elif type_name == "ahu":
        sim.set_ahu_state(zone_name, cmd_data["active"], cmd_data.get("fan_speed"), cmd_data.get("temp_set"))
    elif type_name == "curtain":
        sim.set_curtain_state(zone_name, cmd_data["percentage_cover"])
    elif type_name in ["dht22", "mq2", "lm393"]:
        if cmd_data.get("poll"):
            hex_msg = sim.get_sensor_reading(zone_name, type_name)
            if hex_msg:
                sim.publish_queue.append((zone_code, type_code, hex_msg))

mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

def render_live_header():
    """Redraws fixed status table at lines 1-25 using ANSI cursor positioning"""
    sim_time_str = sim.sim_time.strftime("%Y-%m-%d %H:%M:%S")
    speed_str = f"{sim.time_speed:.1f}x"
    outdoor_rain_str = "RAIN (ON)" if getattr(sim, 'outdoor_rain', 0) == 1 else "CLEAR (OFF)"

    border = "=" * 80
    t_border = "+-----------------+-------+-------+-------------+-------+-------+------------------+"
    header_lines = [
        border,
        "               IOT OBJECT SIMULATOR ENGINE (12 ZONES + BALCONY)                 ",
        border,
        f" Sim Time : {sim_time_str} ({speed_str:<4}) | Out: {sim.outdoor_temp:4.1f}C, {sim.outdoor_humid:4.1f}%, {sim.outdoor_light:5.0f}Lx | {outdoor_rain_str:<10}",
        t_border,
        "|       Zone Name |  Temp | Humid | Illuminance | Smoke | Light |     AirCond (AHU) |",
        t_border
    ]

    for zone in ZONES:
        state = sim.zone_states[zone]
        smoke_str = "SMOKE" if state["smoke"] else "OFF"
        if zone == "balcony":
            light_str = "N/A"
            ahu_str = "N/A"
        else:
            light_str = "ON" if state.get("light_active", False) else "OFF"
            if state.get("ahu_active", False):
                ahu_str = f"ON(Spd:{state.get('ahu_fan_speed',1)},Set:{state.get('ahu_temp_set',25.0):.1f}C)"
            else:
                ahu_str = f"OFF(Set:{state.get('ahu_temp_set',25.0):.1f}C)"

        header_lines.append(f"| {zone:<15} | {state['temp']:5.1f} | {state['humid']:5.1f} | {state['light_intensity']:7} Lux | {smoke_str:<5} |  {light_str:<4} | {ahu_str:<17} |")

    header_lines.append(t_border)

    # Doors status
    door_str = " | ".join([f"{d}: {'OPEN' if info['is_open'] else 'CLOSED'}" for d, info in sim.doors.items()])
    header_lines.append(f" Doors   : {door_str[:68]:<68}")

    # Windows status
    wd_str = " | ".join([f"{wd}: {'OPEN' if info['is_open'] else 'CLOSED'} ({info['curtain_pct']}%)" for wd, info in sim.windows.items()][:3])
    header_lines.append(f" Windows : {wd_str[:68]:<68}")
    header_lines.append(border)
    header_lines.append(" Commands: [light <z> <on/off>]  [ahu <z> <on/off> [spd] [temp]]  [door <1-5>] [q]")
    header_lines.append(border)

    # ANSI Cursor Save: \033[s, Move to top-left: \033[1;1H, Clear line: \033[K, Restore Cursor: \033[u
    buf = "\033[s\033[1;1H"
    for line in header_lines:
        buf += line + "\033[K\n"
    buf += "\033[u"

    sys.stdout.write(buf)
    sys.stdout.flush()

def simulation_loop():
    """Background thread updating simulation physics and rendering live header"""
    global log_hex
    while True:
        sim.update()

        # Publish telemetry frames in queue
        while sim.priority_publish_queue or sim.publish_queue:
            if sim.priority_publish_queue:
                code, type_code, hex_msg = sim.priority_publish_queue.pop(0)
            else:
                code, type_code, hex_msg = sim.publish_queue.pop(0)

            mqtt_client.publish(TOPIC_TELEMETRY, hex_msg)
            time.sleep(0.1)

        # Update live header status table
        render_live_header()
        time.sleep(0.5)

def print_help():
    print("\n================ AVAILABLE OBJECT SIMULATOR COMMANDS ================")
    print(" 1. Light    : `light <zone> <on/off>` (e.g. `light pantry on`)")
    print(" 2. AHU Air  : `ahu <zone> <on/off> [speed 1-3] [temp_set]` (e.g. `ahu pantry on 2 24.5`)")
    print(" 3. Window   : `window <1-6> <open/close>` (e.g. `window 1 open`)")
    print(" 4. Curtain  : `curtain <1-6> <cover_pct 0-100>` (e.g. `curtain 1 80`)")
    print(" 5. Door     : `door <1-5> <open/close>` (e.g. `door 2 open`)")
    print(" 6. Smoke    : `smoke <zone> <on/off>` (e.g. `smoke storage on`)")
    print(" 7. Time Spd : `time speed <val>` (e.g. `time speed 60`)")
    print(" 8. Time Set : `time set <YYYY-MM-DD HH:MM:SS>`")
    print(" 9. Log Hex  : `log <on/off>`")
    print("10. Creds    : `creds` or `creds <zone> <device_type>`")
    print("11. Exit     : `exit` or `quit` or `q`")
    print("====================================================================")

def console_loop():
    """Main interactive console input loop"""
    global log_hex
    while True:
        try:
            sys.stdout.write("\033[27;1H\033[KObjectSim> ")
            sys.stdout.flush()
            cmd_line = input().strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not cmd_line:
            continue

        parts = cmd_line.split()
        cmd = parts[0].lower()

        if cmd in ["exit", "quit", "q"]:
            break
        elif cmd in ["h", "help"]:
            print_help()
        elif cmd == "log":
            if len(parts) > 1 and parts[1].lower() in ["on", "off"]:
                log_hex = (parts[1].lower() == "on")
        elif cmd == "light":
            if len(parts) >= 3:
                zone = parts[1].lower()
                state_str = parts[2].lower()
                if zone in ZONES and state_str in ["on", "off"]:
                    sim.set_light_state(zone, state_str == "on")
        elif cmd == "ahu":
            if len(parts) >= 3:
                zone = parts[1].lower()
                state_str = parts[2].lower()
                if zone in ZONES and state_str in ["on", "off"]:
                    active = (state_str == "on")
                    fan_speed = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None
                    temp_set = float(parts[4]) if len(parts) > 4 else None
                    sim.set_ahu_state(zone, active, fan_speed, temp_set)
        elif cmd == "door":
            if len(parts) >= 3:
                door_num = parts[1]
                state_str = parts[2].lower()
                door_id = f"door_0{door_num}"
                if door_id in sim.doors and state_str in ["open", "close", "closed"]:
                    sim.set_door_state(door_id, state_str == "open")
        elif cmd == "window":
            if len(parts) >= 3:
                wd_num = parts[1]
                state_str = parts[2].lower()
                wd_id = f"wd_0{wd_num}"
                if wd_id in sim.windows and state_str in ["open", "close", "closed"]:
                    sim.set_window_state(wd_id, state_str == "open")
        elif cmd == "curtain":
            if len(parts) >= 3:
                wd_num = parts[1]
                pct_str = parts[2]
                wd_id = f"wd_0{wd_num}"
                if wd_id in sim.windows and pct_str.isdigit():
                    sim.set_curtain_state(wd_id, int(pct_str))
        elif cmd == "smoke":
            if len(parts) >= 3:
                zone = parts[1].lower()
                state_str = parts[2].lower()
                if zone in ZONES and state_str in ["on", "off"]:
                    sim.set_smoke_alarm(zone, state_str == "on")
        elif cmd == "time":
            if len(parts) >= 3:
                sub_cmd = parts[1].lower()
                if sub_cmd == "speed":
                    try:
                        sim.time_speed = float(parts[2])
                    except ValueError:
                        pass
                elif sub_cmd == "set":
                    try:
                        time_str = " ".join(parts[2:])
                        sim.sim_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        pass

        render_live_header()

def main():
    print("Connecting to MQTT Broker: " + MQTT_BROKER + "...", flush=True)
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
    except Exception as e:
        print(f"[ERROR] Cannot connect to MQTT Broker: {e}", flush=True)
        sys.exit(1)

    connected_event.wait(timeout=10.0)

    # Reserve screen space and clear screen
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.write("\n" * 27)
    sys.stdout.write("ObjectSim> ")
    sys.stdout.flush()

    t = threading.Thread(target=simulation_loop, daemon=True)
    t.start()

    try:
        if sys.stdin is not None and sys.stdin.isatty():
            console_loop()
        else:
            while True:
                time.sleep(1)
    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        print("IoT Object Simulator stopped successfully.")

if __name__ == "__main__":
    main()
