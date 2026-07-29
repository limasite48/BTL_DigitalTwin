import math
import time
import random
from datetime import datetime
from config import LATITUDE, LONGITUDE, TIMEZONE_OFFSET

class SolarEngine:
    """
    Astronomical Solar Engine calculating Sun Azimuth, Elevation angle,
    and Direct Solar Irradiance / Lux based on NOAA formulas in pure Python.
    """
    def __init__(self, lat: float = LATITUDE, lon: float = LONGITUDE, tz_offset: float = TIMEZONE_OFFSET):
        self.lat = lat
        self.lon = lon
        self.tz_offset = tz_offset

    def calculate_sun_position(self, sim_time: datetime) -> dict:
        """
        Calculates sun position and irradiance for a given simulation time.
        Returns dict: {"azimuth": float, "elevation": float, "solar_irradiance_lux": float}
        """
        # Day of year (1 - 365/366)
        day_of_year = sim_time.timetuple().tm_yday
        hour = sim_time.hour + sim_time.minute / 60.0 + sim_time.second / 3600.0

        # Fractional year (gamma) in radians
        gamma = (2.0 * math.pi / 365.0) * (day_of_year - 1 + (hour - 12.0) / 24.0)

        # Equation of time (eqtime) in minutes
        eqtime = 229.18 * (
            0.000075
            + 0.001868 * math.cos(gamma)
            - 0.032077 * math.sin(gamma)
            - 0.014615 * math.cos(2 * gamma)
            - 0.040849 * math.sin(2 * gamma)
        )

        # Solar declination angle in radians
        decl = (
            0.006918
            - 0.399912 * math.cos(gamma)
            + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma)
            + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma)
            + 0.00148 * math.sin(3 * gamma)
        )

        # True Solar Time in minutes
        local_time_min = sim_time.hour * 60.0 + sim_time.minute + sim_time.second / 60.0
        time_offset = eqtime + 4.0 * self.lon - 60.0 * self.tz_offset
        tst = local_time_min + time_offset

        # Solar Hour Angle (ha) in degrees
        ha_deg = (tst / 4.0) - 180.0
        ha_rad = math.radians(ha_deg)

        # Latitude in radians
        lat_rad = math.radians(self.lat)

        # Solar Zenith Angle
        cos_zenith = math.sin(lat_rad) * math.sin(decl) + math.cos(lat_rad) * math.cos(decl) * math.cos(ha_rad)
        cos_zenith = max(-1.0, min(1.0, cos_zenith))
        zenith_rad = math.acos(cos_zenith)

        # Solar Elevation Angle
        elevation_deg = 90.0 - math.degrees(zenith_rad)

        # Solar Azimuth Angle
        sin_zenith = math.sin(zenith_rad)
        if sin_zenith < 1e-6:
            azimuth_deg = 180.0
        else:
            cos_azimuth = (math.sin(lat_rad) * cos_zenith - math.sin(decl)) / (math.cos(lat_rad) * sin_zenith)
            cos_azimuth = max(-1.0, min(1.0, cos_azimuth))
            azimuth_deg = math.degrees(math.acos(cos_azimuth))
            if ha_deg > 0:
                azimuth_deg = (360.0 - azimuth_deg) % 360.0
            else:
                azimuth_deg = azimuth_deg % 360.0

        # Direct Irradiance and Lux calculation
        if elevation_deg > 0:
            sin_elev = math.sin(math.radians(elevation_deg))
            # Atmospheric Air Mass model (Kasten-Young)
            air_mass = 1.0 / (sin_elev + 0.50572 * (max(0.1, elevation_deg) + 6.07995) ** (-1.6364))
            # Direct irradiance in W/m2 (Solar constant I0 ~ 1361 W/m2)
            direct_irradiance = 1361.0 * (0.7 ** (air_mass ** 0.67)) * sin_elev
            # Conversion: 1 W/m2 ≈ 120 Lux for natural daylight spectrum
            solar_lux = direct_irradiance * 120.0
        else:
            # Dense urban commercial center night light (streetlights, commercial LED signs, neon, skyglow: 100.0 - 150.0 Lux)
            base_night_lux = 125.0 + 20.0 * math.sin(time.time() / 8.0)
            solar_lux = max(100.0, base_night_lux + random.uniform(-5.0, 5.0))

        return {
            "azimuth": round(azimuth_deg, 2),
            "elevation": round(elevation_deg, 2),
            "solar_irradiance_lux": round(solar_lux, 1)
        }
