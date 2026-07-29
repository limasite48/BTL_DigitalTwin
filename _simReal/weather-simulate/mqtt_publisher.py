import json
import logging
import threading
import paho.mqtt.client as mqtt
from config import MQTT_BROKER, MQTT_PORT, TOPIC_WEATHER_STATE

logger = logging.getLogger(__name__)

class WeatherMqttPublisher:
    """
    Mosquitto MQTT Publisher Client for publishing IPC weather state to topic simreal/weather/state.
    """
    def __init__(self, broker: str = MQTT_BROKER, port: int = MQTT_PORT, topic: str = TOPIC_WEATHER_STATE):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="simreal_weather_engine")
        self.connected = False
        self.connected_event = threading.Event()

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.connected = True
            self.connected_event.set()
            self.client.subscribe("simreal/weather/cmd")
            logger.info(f"Connected successfully to Mosquitto MQTT Broker [{self.broker}:{self.port}]")
        else:
            logger.error(f"Failed to connect to MQTT Broker, return code: {rc}")

    def set_cmd_callback(self, callback):
        self.cmd_callback = callback
        self.client.on_message = self._on_message

    def _on_message(self, client, userdata, msg):
        if msg.topic == "simreal/weather/cmd" and hasattr(self, 'cmd_callback'):
            try:
                payload = json.loads(msg.payload.decode('utf-8'))
                self.cmd_callback(payload)
            except Exception as e:
                logger.error(f"Error parsing weather cmd: {e}")

    def _on_disconnect(self, client, userdata, disconnect_flags, rc, properties=None):
        self.connected = False
        self.connected_event.clear()
        logger.warning(f"Disconnected from MQTT Broker, return code: {rc}")

    def connect(self):
        """Starts asynchronous MQTT connection loop and waits up to 3s for connection"""
        try:
            self.client.connect_async(self.broker, self.port, keepalive=60)
            self.client.loop_start()
            self.connected_event.wait(timeout=3.0)
        except Exception as e:
            logger.error(f"Failed to initialize MQTT connection: {e}")

    def publish_weather_state(self, payload: dict) -> bool:
        """Publishes weather state JSON payload over MQTT IPC"""
        if not self.connected:
            logger.debug("MQTT broker not connected yet, skipping publish cycle.")
            return False

        try:
            json_str = json.dumps(payload, ensure_ascii=False)
            res = self.client.publish(self.topic, json_str, qos=0)
            return res.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            logger.error(f"Error publishing weather state payload: {e}")
            return False

    def disconnect(self):
        """Gracefully disconnects MQTT client"""
        self.client.loop_stop()
        self.client.disconnect()
