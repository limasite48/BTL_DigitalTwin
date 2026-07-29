import os
import sys
import time
import argparse
import logging
import threading
from datetime import datetime, timedelta, timezone

# Enable UTF-8 encoding and ANSI Virtual Terminal sequences on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stdin, 'reconfigure'):
    sys.stdin.reconfigure(encoding='utf-8')
os.system('')  # Enable ANSI VT100 escape sequences in Windows CMD

from config import UPDATE_INTERVAL_SEC, DEFAULT_TIME_SPEED, TOPIC_WEATHER_STATE
from solar_engine import SolarEngine
from weather_engine import WeatherEngine
from mqtt_publisher import WeatherMqttPublisher

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("WeatherSim")

class WeatherSimulationManager:
    def __init__(self, start_time: datetime, speed: float, initial_rain: bool):
        self.solar_engine = SolarEngine()
        self.weather_engine = WeatherEngine()
        self.mqtt_publisher = WeatherMqttPublisher()

        if initial_rain:
            self.weather_engine.set_rain_state(True)

        self.sim_time = start_time
        self.time_speed = speed
        self.running = True
        self.last_real_time = time.time()
        self.last_payload = {}
        self.last_sent_ok = False
        self.lock = threading.Lock()
        self.cmd_feedback = ""

    def simulation_loop(self):
        """Background thread updating physics simulation, MQTT IPC, and live header UI"""
        while self.running:
            now_real = time.time()
            dt_real = now_real - self.last_real_time
            self.last_real_time = now_real

            # Update simulation clock
            dt_sim = dt_real * self.time_speed
            with self.lock:
                self.sim_time += timedelta(seconds=dt_sim)

            # 1. Calculate Sun astronomical position
            sun_data = self.solar_engine.calculate_sun_position(self.sim_time)

            # 2. Calculate Atmosphere parameters & Lux attenuation
            atmosphere, effective_lux = self.weather_engine.calculate_atmosphere(self.sim_time, sun_data)

            # Construct standardized JSON payload
            now_utc = datetime.now(timezone.utc)
            with self.lock:
                self.last_payload = {
                    "timestamp": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "sim_time": self.sim_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "speed": self.time_speed,
                    "sun": {
                        "azimuth": sun_data["azimuth"],
                        "elevation": sun_data["elevation"],
                        "solar_irradiance_lux": effective_lux
                    },
                    "atmosphere": atmosphere
                }

            # 3. Publish weather state over MQTT IPC
            self.last_sent_ok = self.mqtt_publisher.publish_weather_state(self.last_payload)

            # 4. Redraw live fixed header at top of terminal
            self.render_live_header()

            time.sleep(UPDATE_INTERVAL_SEC)

    def render_live_header(self):
        """Redraws fixed status table at line 1 of terminal using ANSI cursor positioning"""
        with self.lock:
            if not self.last_payload:
                return

            sun = self.last_payload.get("sun", {})
            atm = self.last_payload.get("atmosphere", {})
            rain_str = "RAIN (ON)" if atm.get("rain_state") == 1 else "CLEAR (OFF)"
            mqtt_str = "OK" if self.last_sent_ok else "WAIT (Broker Offline)"
            sim_time_str = self.sim_time.strftime("%Y-%m-%d %H:%M:%S")
            speed = self.time_speed

        border = "=" * 80
        header_lines = [
            border,
            "              SIMREAL WEATHER SIMULATOR ENGINE (PHYSICAL REALITY)               ",
            border,
            f" Sim Time  : {sim_time_str} ({speed:4.1f}x) | MQTT IPC: {TOPIC_WEATHER_STATE} [{mqtt_str:<4}]",
            f" Sun       : Elev: {sun.get('elevation', 0.0):5.1f} deg | Azim: {sun.get('azimuth', 0.0):5.1f} deg | Lux: {sun.get('solar_irradiance_lux', 0.0):8.1f}",
            f" Atmosphere: Temp: {atm.get('temperature', 0.0):4.1f} C | Humid: {atm.get('humidity', 0.0):4.1f}% | Weather: {rain_str:<10}",
            border,
            " Commands  : [rain on/off]  [speed <val>]  [settime YYYY-MM-DD HH:MM:SS]  [q/exit]",
            border
        ]

        # ANSI Cursor Save: \033[s, Move to top-left: \033[1;1H, Clear line: \033[K, Restore Cursor: \033[u
        buf = "\033[s\033[1;1H"
        for line in header_lines:
            buf += line + "\033[K\n"
        if self.cmd_feedback:
            buf += f" Feedback  : {self.cmd_feedback[:65]}\033[K\n"
        else:
            buf += "\033[K\n"
        buf += "\033[u"

        sys.stdout.write(buf)
        sys.stdout.flush()

def main():
    parser = argparse.ArgumentParser(description="Outdoor Weather & Sun Engine (_simReal/weather-simulate)")
    parser.add_argument("--speed", type=float, default=DEFAULT_TIME_SPEED, help="Simulation time speed multiplier")
    parser.add_argument("--rain", action="store_true", help="Start simulation with Rain weather state active")
    parser.add_argument("--start-time", type=str, default="2026-07-01T08:00:00", help="Start time (ISO format YYYY-MM-DDTHH:MM:SS)")
    args = parser.parse_args()

    try:
        start_time = datetime.fromisoformat(args.start_time)
    except ValueError:
        start_time = datetime(2026, 7, 1, 8, 0, 0)

    sim_mgr = WeatherSimulationManager(start_time, args.speed, args.rain)

    def handle_ipc_cmd(payload):
        cmd = payload.get("command")
        val = payload.get("value")
        if cmd == "mode":
            sim_mgr.weather_engine.set_weather_mode(str(val))
        elif cmd == "fog":
            sim_mgr.weather_engine.set_weather_mode("fog")
        elif cmd == "rain":
            if val == "on" or val is True:
                sim_mgr.weather_engine.set_weather_mode("rain")
            elif val == "off" or val is False:
                sim_mgr.weather_engine.set_weather_mode("clear")
            else:
                sim_mgr.weather_engine.set_weather_mode(str(val))
        elif cmd == "clear":
            sim_mgr.weather_engine.set_weather_mode("clear")
        elif cmd == "speed":
            try:
                sim_mgr.time_speed = float(val)
            except ValueError:
                pass
        elif cmd == "settime":
            try:
                dt = datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
                with sim_mgr.lock:
                    sim_mgr.sim_time = dt
            except ValueError:
                pass

    sim_mgr.mqtt_publisher.set_cmd_callback(handle_ipc_cmd)
    sim_mgr.mqtt_publisher.connect()

    # Start background simulation loop thread
    sim_thread = threading.Thread(target=sim_mgr.simulation_loop, daemon=True)
    sim_thread.start()

    # Headless mode check
    if sys.stdin is None or not sys.stdin.isatty():
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            pass
        return

    # Clear screen and reserve space for live header
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.write("\n" * 12)
    sys.stdout.write("WeatherSim> ")
    sys.stdout.flush()

    try:
        while True:
            try:
                sys.stdout.write("\033[12;1H\033[KWeatherSim> ")
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
                sim_mgr.cmd_feedback = "Commands: rain on/off, speed <val>, settime YYYY-MM-DD HH:MM:SS, exit"
            elif cmd == "rain":
                if len(parts) >= 2 and parts[1].lower() in ["on", "off"]:
                    is_rain = (parts[1].lower() == "on")
                    sim_mgr.weather_engine.set_rain_state(is_rain)
                    sim_mgr.cmd_feedback = f"Rain state set to {'ON' if is_rain else 'OFF'}"
                else:
                    sim_mgr.cmd_feedback = "Usage: `rain on` or `rain off`"
            elif cmd == "speed":
                if len(parts) >= 2:
                    try:
                        spd = float(parts[1])
                        sim_mgr.time_speed = spd
                        sim_mgr.cmd_feedback = f"Simulation speed set to {spd}x"
                    except ValueError:
                        sim_mgr.cmd_feedback = "Speed must be a number."
                else:
                    sim_mgr.cmd_feedback = "Usage: `speed <multiplier>`"
            elif cmd == "settime":
                if len(parts) >= 3:
                    try:
                        time_str = " ".join(parts[1:])
                        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                        with sim_mgr.lock:
                            sim_mgr.sim_time = dt
                        sim_mgr.cmd_feedback = f"Time set to {dt.strftime('%Y-%m-%d %H:%M:%S')}"
                    except ValueError:
                        sim_mgr.cmd_feedback = "Format: YYYY-MM-DD HH:MM:SS"
                else:
                    sim_mgr.cmd_feedback = "Usage: `settime YYYY-MM-DD HH:MM:SS`"
            else:
                sim_mgr.cmd_feedback = f"Unknown command '{cmd}'. Try: rain, speed, settime, q"

            # Immediately refresh live header with feedback
            sim_mgr.render_live_header()

    finally:
        sim_mgr.running = False
        sim_mgr.mqtt_publisher.disconnect()
        sys.stdout.write("\033[14;1H\nWeather Simulator Engine stopped.\n")

if __name__ == "__main__":
    main()
