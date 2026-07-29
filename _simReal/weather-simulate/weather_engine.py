import math
import random
from datetime import datetime
from config import HANOI_BASE_TEMP

class WeatherEngine:
    """
    Atmospheric Weather Engine simulating outdoor parameters (Temperature, Humidity, Rain, Cloud, Wind).
    Provides smooth continuous transitions between Clear Sky, Dense Fog, and Heavy Rain.
    """
    def __init__(self):
        self.target_rain_state = 0     # Target: 0 (Clear/Fog) or 1 (Raining)
        self.rain_state = 0            # Effective state: 0 (Clear/Fog) or 1 (Raining)
        self.weather_mode = "clear"    # "clear", "fog", "rain"
        
        # Current continuous atmospheric variables
        self.rain_intensity_mmh = 0.0  # Current Rain intensity (mm/h)
        self.cloud_cover_pct = 15.0    # Current Cloud cover (%)
        self.wind_speed_ms = 2.5       # Wind speed (m/s)

        # Targets for smooth dynamic transition
        self.target_cloud_cover = 15.0
        self.target_rain_intensity = 0.0
        self.target_temp_drop = 0.0
        self.target_humid_boost = 0.0

        # Smooth transition state variables
        self.current_temp_drop = 0.0
        self.current_humid_boost = 0.0

    def set_weather_mode(self, mode_str: str):
        """Set target weather mode (clear / fog / rain) and initiate smooth transition"""
        mode = str(mode_str).lower().strip()
        if mode == "fog":
            self.weather_mode = "fog"
            self.target_rain_state = 0
            self.target_cloud_cover = 95.0
            self.target_rain_intensity = 0.0
            self.target_temp_drop = 0.0
            self.target_humid_boost = 35.0
        elif mode in ["rain", "heavy_rain", "1"]:
            self.weather_mode = "rain"
            self.target_rain_state = 1
            self.target_cloud_cover = 90.0
            self.target_rain_intensity = 20.0
            self.target_temp_drop = 3.5
            self.target_humid_boost = 25.0
        else: # clear
            self.weather_mode = "clear"
            self.target_rain_state = 0
            self.target_cloud_cover = 15.0
            self.target_rain_intensity = 0.0
            self.target_temp_drop = 0.0
            self.target_humid_boost = 0.0

    def set_rain_state(self, is_raining: bool):
        """Legacy helper matching rain toggle"""
        self.set_weather_mode("rain" if is_raining else "clear")

    def calculate_atmosphere(self, sim_time: datetime, sun_data: dict) -> tuple[dict, float]:
        month = sim_time.month
        hour = sim_time.hour + sim_time.minute / 60.0 + sim_time.second / 3600.0

        # Continuous smooth dynamic transition (Exponential lerp)
        lerp_rate = 0.05
        self.cloud_cover_pct += lerp_rate * (self.target_cloud_cover - self.cloud_cover_pct)
        self.rain_intensity_mmh += lerp_rate * (self.target_rain_intensity - self.rain_intensity_mmh)
        self.current_temp_drop += lerp_rate * (self.target_temp_drop - self.current_temp_drop)
        self.current_humid_boost += lerp_rate * (self.target_humid_boost - self.current_humid_boost)

        # Derive effective rain_state (0 = Clear/Drizzle < 2mm/h, 1 = Active Rain >= 2mm/h)
        self.rain_state = 1 if self.rain_intensity_mmh >= 2.0 else 0

        # Base temperature & humidity for current month
        base_temp = HANOI_BASE_TEMP.get(month, 28.0)
        temp_range = 6.0

        hour_rad = (hour - 14.0) * (2.0 * math.pi / 24.0)
        clear_sky_temp = base_temp + (temp_range / 2.0) * math.cos(hour_rad)
        clear_sky_humid = max(40.0, min(80.0, 75.0 - 15.0 * math.cos(hour_rad)))

        temp = clear_sky_temp - self.current_temp_drop
        humidity = min(98.0, clear_sky_humid + self.current_humid_boost)

        self.wind_speed_ms = round(max(0.5, min(10.0, self.wind_speed_ms + random.uniform(-0.1, 0.1))), 1)

        # Cloud cover attenuation on solar illuminance (Lux)
        base_lux = sun_data.get("solar_irradiance_lux", 0.0)
        cloud_attenuation = 1.0 - (self.cloud_cover_pct / 100.0) * 0.78
        effective_lux = max(4.0, base_lux * cloud_attenuation)

        atmosphere = {
            "weather_mode": self.weather_mode,
            "temperature": round(temp, 1),
            "humidity": round(humidity, 1),
            "rain_state": self.rain_state,
            "rain_intensity_mmh": round(self.rain_intensity_mmh, 1),
            "cloud_cover_pct": round(self.cloud_cover_pct, 1),
            "wind_speed_ms": self.wind_speed_ms
        }

        return atmosphere, round(effective_lux, 1)
