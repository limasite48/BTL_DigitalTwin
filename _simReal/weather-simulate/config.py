# Configuration for Sun & Weather Simulation Module (_simReal/weather-simulate)

# Mosquitto MQTT Broker Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
TOPIC_WEATHER_STATE = "simreal/weather/state"

# Geographic Coordinates: HCMC, Vietnam
LATITUDE = 10.7831      # Latitude (North)
LONGITUDE = 106.6917    # Longitude (East)
TIMEZONE_OFFSET = 7.0   # Timezone UTC+7

# Simulation Time & Loop Configuration
UPDATE_INTERVAL_SEC = 1.0   # IPC Publish Interval (real-time seconds)
DEFAULT_TIME_SPEED = 1.0    # Simulation speed multiplier (1.0 = real-time, 60.0 = 1s real is 1m sim)

# Monthly Average Base Temperatures for HCMC (°C)
HANOI_BASE_TEMP = {
    1: 26.5, 2: 27.5, 3: 28.5, 4: 29.5,
    5: 29.0, 6: 28.5, 7: 28.0, 8: 28.0,
    9: 27.5, 10: 27.5, 11: 27.0, 12: 26.0
}
