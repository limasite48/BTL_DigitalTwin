import sys
import os
import time
import threading
import json
from datetime import datetime

# Ensure UTF-8 stdout/stdin encoding for cross-platform compatibility
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stdin, 'reconfigure'):
    sys.stdin.reconfigure(encoding='utf-8')
os.system('')  # Enable VT100 ANSI escape sequences in Windows CMD

# Add current directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import paho.mqtt.client as mqtt
from config import (
    MQTT_BROKER, MQTT_PORT, TOPIC_ZIGBEE_TELEMETRY, TOPIC_ZIGBEE_COMMAND,
    TOPIC_SERVER_SEND, TOPIC_SERVER_RECEIVE,
    ZONES, ZONE_CODES, TYPE_CODES, CODE_TO_ZONE, CODE_TO_TYPE
)
from protocol import (
    parse_uplink_frame, decode_uplink_payload,
    encode_downlink_command, wrap_downlink_frame
)
from gateway import GatewayEngine
import backend_adapter as ba

# Initialize Gateway engine
gateway = GatewayEngine()
log_packets = False
connected_event = threading.Event()
pending_commands = {}
pending_commands_lock = threading.Lock()
mtls_handshake_done = False

def is_state_matching(device_type, emu_cmd, decoded_data):
    if device_type == "light":
        expected_status = "ON" if emu_cmd.get("active") else "OFF"
        return decoded_data.get("status") == expected_status
    elif device_type == "ahu":
        expected_status = "ON" if emu_cmd.get("active") else "OFF"
        if decoded_data.get("status") != expected_status:
            return False
        if emu_cmd.get("fan_speed") is not None and decoded_data.get("fan_speed") != emu_cmd.get("fan_speed"):
            return False
        if emu_cmd.get("temp_set") is not None and abs(decoded_data.get("temp_set", 0.0) - emu_cmd.get("temp_set")) > 0.1:
            return False
        return True
    elif device_type == "curtain":
        expected_pct = emu_cmd.get("percentage_cover")
        return decoded_data.get("percentage_cover") == expected_pct
    return True

def on_connect(client, userdata, flags, rc, properties=None):
    client.subscribe(TOPIC_ZIGBEE_TELEMETRY)
    client.subscribe(TOPIC_SERVER_RECEIVE)
    client.subscribe("iot/handshake/server")
    client.subscribe(ba.BACKEND_COMMAND_SUB)
    client.subscribe("duk1chvietcong/hcmc_office/gw_cmd")

    import hashlib
    cert_hash = hashlib.sha256(b"gw_hcmc_office_certificate_pem").hexdigest()
    handshake_payload = json.dumps({
        "gateway_id": "gw_hcmc_office",
        "cert_hash": cert_hash
    })
    client.publish("iot/handshake/gateway", handshake_payload)
    connected_event.set()

def on_message(client, userdata, msg):
    global log_packets, mtls_handshake_done

    if msg.topic == TOPIC_ZIGBEE_TELEMETRY:
        payload_str = msg.payload.decode("utf-8", errors="ignore").strip()
        data_bytes = bytes.fromhex(payload_str.replace(" ", ""))
        if len(data_bytes) < 4:
            return
        zone_id = data_bytes[1]
        type_code = data_bytes[2]
        zone_name = CODE_TO_ZONE.get(zone_id)
        type_name = CODE_TO_TYPE.get(type_code)

        if not zone_name or not type_name:
            return

        key = gateway.get_device_key(zone_name, type_name)
        if not key:
            return

        parsed = parse_uplink_frame(payload_str, key)
        if not parsed:
            return

        decoded = decode_uplink_payload(type_code, parsed["payload"])
        if not decoded:
            return

        with pending_commands_lock:
            matched_keys = []
            for cmd_id, cmd_info in pending_commands.items():
                if cmd_info["zone"] == zone_name and cmd_info["device_type"] == type_name:
                    if is_state_matching(type_name, cmd_info["command"], decoded):
                        matched_keys.append(cmd_id)

            for cmd_id in matched_keys:
                cmd_info = pending_commands.pop(cmd_id)
                ba.publish_command_ack(mqtt_client, cmd_info["backend_id"], "SUCCESS", "Command executed successfully by hardware")

        # Update Device Shadow and apply edge filter
        gateway.process_device_update(zone_id, type_code, decoded)

        # Build and publish telemetry to Backend
        res_backend = ba.build_telemetry(zone_name, type_name, decoded)
        if res_backend:
            t_topic, t_json = res_backend
            if gateway.network_connected:
                mqtt_client.publish(t_topic, t_json)
                gateway.stats["tx_server"] += 1

    elif msg.topic == ba.BACKEND_COMMAND_SUB:
        payload_str = msg.payload.decode("utf-8", errors="ignore").strip()
        backend_cmd = ba.parse_backend_command(payload_str)
        if not backend_cmd:
            return

        device_id = backend_cmd["deviceId"]
        cmd_type = backend_cmd["commandType"]
        params = backend_cmd["parameters"]

        zone_name, dev_type = ba.parse_device_id(device_id)
        if not zone_name or not dev_type:
            return

        hex_cmd, err = ba.convert_backend_cmd_to_hex(zone_name, dev_type, cmd_type, params, gateway)
        if err:
            ba.publish_command_ack(mqtt_client, backend_cmd["backend_cmd_id"], "FAILED", err)
            return

        ba.publish_command_ack(mqtt_client, backend_cmd["backend_cmd_id"], "RECEIVED", "Command accepted by Gateway")

        with pending_commands_lock:
            pending_commands[backend_cmd["backend_cmd_id"]] = {
                "backend_id": backend_cmd["backend_cmd_id"],
                "zone": zone_name,
                "device_type": dev_type,
                "command": params,
                "send_time": time.time()
            }

        mqtt_client.publish(TOPIC_ZIGBEE_COMMAND, hex_cmd)

    elif msg.topic == "iot/handshake/server":
        mtls_handshake_done = True

    elif msg.topic == "duk1chvietcong/hcmc_office/gw_cmd":
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            cmd = payload.get("command")
            if cmd == "network":
                state = (payload.get("state") == "on")
                gateway.network_connected = state
                if state:
                    gateway.sync_offline_data()
            elif cmd == "pair":
                gateway.pair_device(payload.get("mac", ""), payload.get("install_code", ""))
            elif cmd == "unpair":
                gateway.unpair_device(payload.get("target", ""))
        except Exception:
            pass

mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

def render_live_header():
    """Redraws fixed status table at lines 1-25 using ANSI cursor positioning"""
    conn_str = "ONLINE" if gateway.network_connected else "OFFLINE"
    stats = gateway.stats
    paired_cnt = len(gateway.paired_devices)

    border = "=" * 80
    t_border = "+-----------------+-------+-------+-------------+-------+-------+------------------+"
    header_lines = [
        border,
        "                       IOT GATEWAY SIMULATOR ENGINE (EDGE SHADOW)               ",
        border,
        f" Server Conn : {conn_str:<7} | Paired: {paired_cnt:<2} | RX: {stats['rx_zigbee']:<5} | Filt: {stats['filtered']:<5} | TX: {stats['tx_server']:<5}",
        t_border,
        "|       Zone Name |  Temp | Humid | Illuminance | Smoke | Light |     AirCond (AHU) |",
        t_border
    ]

    for zone in ZONES:
        data = gateway.state_document["zones"][zone]
        temp_val = data["temp"]
        humid_val = data["humid"]
        light_val = data["light_intensity"]
        smoke_str = "SMOKE" if data["smoke"] is True else ("OFF" if data["smoke"] is False else "N/A")

        lamp_val = data["light"]
        light_str = lamp_val.get("status", "N/A") if isinstance(lamp_val, dict) else "N/A"

        ahu_val = data["ahu"]
        if isinstance(ahu_val, dict):
            ahu_str = f"{ahu_val.get('status')}(Spd:{ahu_val.get('fan_speed')},Set:{ahu_val.get('temp_set'):.1f}C)"
        else:
            ahu_str = "N/A"

        temp_part = f"{temp_val:5.1f}" if temp_val is not None else "  N/A"
        humid_part = f"{humid_val:5.1f}" if humid_val is not None else "  N/A"
        light_part = f"{light_val:7}" if light_val is not None else "    N/A"

        header_lines.append(f"| {zone:<15} | {temp_part} | {humid_part} | {light_part} Lux | {smoke_str:<5} |  {light_str:<4} | {ahu_str:<17} |")

    header_lines.append(t_border)

    # Doors status
    doors_list = [f"door_0{i}: {gateway.state_document['doors'][f'door_0{i}'].get('status', 'N/A').upper()}" for i in range(1, 6)]
    header_lines.append(f" Doors   : {' | '.join(doors_list)[:68]:<68}")

    # Windows status
    wd_list = []
    for i in range(1, 4):
        w_data = gateway.state_document["windows"][f"wd_0{i}"]
        curt_val = w_data.get("curtain")
        c_str = f"{curt_val.get('percentage_cover')}%" if isinstance(curt_val, dict) else "N/A"
        wd_list.append(f"wd_0{i}: {w_data.get('status', 'N/A').upper()} ({c_str})")
    header_lines.append(f" Windows : {' | '.join(wd_list)[:68]:<68}")
    header_lines.append(border)
    header_lines.append(" Commands: [pair <MAC> <INST>]  [unpair <MAC>]  [network on/off]  [log on/off]  [q]")
    header_lines.append(border)

    # ANSI Cursor Save: \033[s, Move to top-left: \033[1;1H, Clear line: \033[K, Restore Cursor: \033[u
    buf = "\033[s\033[1;1H"
    for line in header_lines:
        buf += line + "\033[K\n"
    buf += "\033[u"

    sys.stdout.write(buf)
    sys.stdout.flush()

def gateway_loop():
    while True:
        if gateway.pending_publish and gateway.network_connected:
            gateway.pending_publish = False
            delta_payload = gateway.get_delta_payload()
            if delta_payload and (delta_payload.get("zones") or delta_payload.get("doors") or delta_payload.get("windows")):
                payload_str = json.dumps(delta_payload, ensure_ascii=False)
                mqtt_client.publish(TOPIC_SERVER_SEND, payload_str)
                gateway.stats["tx_server"] += 1

        with pending_commands_lock:
            now_time = time.time()
            timed_out_ids = []
            for cmd_id, cmd_info in pending_commands.items():
                if now_time - cmd_info["send_time"] > 4.0:
                    timed_out_ids.append(cmd_id)

            for cmd_id in timed_out_ids:
                cmd_info = pending_commands.pop(cmd_id)
                ba.publish_command_ack(mqtt_client, cmd_info["backend_id"], "TIMEOUT", "Hardware execution ACK timed out (4s)")

        render_live_header()
        time.sleep(0.5)

def heartbeat_loop():
    while True:
        if gateway.network_connected:
            for dev_id in ba.HEARTBEAT_DEVICES:
                topic, payload = ba.build_heartbeat(dev_id)
                mqtt_client.publish(topic, payload)
                time.sleep(0.02)
        time.sleep(15)

def polling_loop():
    while True:
        time.sleep(10)

def print_help():
    print("\n================ GATEWAY COMMAND MENU ================")
    print(" 1. Network : `network <on/off>` (Toggle connection to Server)")
    print(" 2. Pair    : `pair <MAC> <INSTALL_CODE>` (e.g. `pair 0100000411 INST_OFFICE_1_DHT22`)")
    print(" 3. Unpair  : `unpair <MAC>` or `unpair <zone> <device>`")
    print(" 4. Log     : `log <on/off>` (Toggle raw Zigbee packet log)")
    print(" 5. Help    : `help` or `h`")
    print(" 6. Exit    : `exit` or `quit` or `q`")
    print("======================================================")

def console_loop():
    global log_packets
    while True:
        try:
            sys.stdout.write("\033[27;1H\033[KGateway> ")
            sys.stdout.flush()
            cmd_line = input().strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not cmd_line:
            continue

        parts = cmd_line.split(maxsplit=1)
        cmd = parts[0].lower()

        if cmd in ["exit", "quit", "q"]:
            break
        elif cmd in ["h", "help"]:
            print_help()
        elif cmd == "log":
            if len(parts) > 1 and parts[1].lower() in ["on", "off"]:
                log_packets = (parts[1].lower() == "on")
        elif cmd == "network":
            if len(parts) > 1 and parts[1].lower() in ["on", "off"]:
                state = (parts[1].lower() == "on")
                gateway.network_connected = state
                if state:
                    gateway.sync_offline_data()
        elif cmd == "pair":
            if len(parts) > 1:
                args = parts[1].split()
                if len(args) == 2:
                    gateway.pair_device(args[0], args[1])
        elif cmd == "unpair":
            if len(parts) > 1:
                gateway.unpair_device(parts[1])

        render_live_header()

def main():
    print("Connecting to MQTT Broker: " + MQTT_BROKER + "...", flush=True)
    try:
        mqtt_client.will_set("iot/status/gw_hcmc_office", json.dumps({"status": "OFFLINE"}), qos=1, retain=True)
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
    except Exception as e:
        print(f"[ERROR] Cannot connect to MQTT Broker: {e}", flush=True)
        sys.exit(1)

    connected_event.wait(timeout=10.0)

    # Reserve screen space and clear screen
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.write("\n" * 27)
    sys.stdout.write("Gateway> ")
    sys.stdout.flush()

    t = threading.Thread(target=gateway_loop, daemon=True)
    t.start()
    hb = threading.Thread(target=heartbeat_loop, daemon=True)
    hb.start()
    pl = threading.Thread(target=polling_loop, daemon=True)
    pl.start()

    try:
        if sys.stdin is not None and sys.stdin.isatty():
            console_loop()
        else:
            while True:
                time.sleep(1)
    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        print("IoT Gateway Simulator stopped successfully.")

if __name__ == "__main__":
    main()
