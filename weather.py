"""Support for Buienradar.nl weather service."""

from datetime import timedelta
import logging

from TISControlProtocol.api import TISApi, TISPacket
from TISControlProtocol.Protocols.udp.ProtocolHandler import TISProtocolHandler

from homeassistant.components.weather import (
    ATTR_CONDITION_CLOUDY,
    ATTR_CONDITION_EXCEPTIONAL,
    ATTR_CONDITION_FOG,
    ATTR_CONDITION_HAIL,
    ATTR_CONDITION_LIGHTNING,
    ATTR_CONDITION_LIGHTNING_RAINY,
    ATTR_CONDITION_PARTLYCLOUDY,
    ATTR_CONDITION_POURING,
    ATTR_CONDITION_RAINY,
    ATTR_CONDITION_SNOWY,
    ATTR_CONDITION_SNOWY_RAINY,
    ATTR_CONDITION_SUNNY,
    ATTR_CONDITION_WINDY,
    ATTR_CONDITION_WINDY_VARIANT,
    ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_NATIVE_PRECIPITATION,
    ATTR_FORECAST_NATIVE_TEMP,
    ATTR_FORECAST_NATIVE_TEMP_LOW,
    ATTR_FORECAST_NATIVE_WIND_SPEED,
    ATTR_FORECAST_TIME,
    ATTR_FORECAST_WIND_BEARING,
    Forecast,
    UnitOfTemperature,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    MATCH_ALL,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    Platform,
    UnitOfLength,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from . import TISConfigEntry

handler = TISProtocolHandler()


async def async_setup_entry(
    hass: HomeAssistant, entry: TISConfigEntry, async_add_devices: AddEntitiesCallback
) -> None:
    """Set up the tis weather platform."""
    tis_api: TISApi = entry.runtime_data.api

    weather_entities = [
        TISWeatherStation(api=tis_api, device_id=[1, 254], gateway="192.168.1.4"),
    ]
    async_add_devices(weather_entities, update_before_add=True)


class TISWeatherStation(WeatherEntity):
    """Representation of a weather condition."""

    def __init__(self, api: TISApi, device_id: list, gateway) -> None:
        """Initialize the weather entity."""
        self.api = api
        self.device_id = device_id
        self.gateway = gateway
        self.update_packet = handler.generate_weather_update_packet(self)
        self.listener = None

        self._attr_unit_of_measurement = UnitOfTemperature.CELSIUS
        # set update interval
        self._attr_update_interval = timedelta(seconds=10)
        async_track_time_interval(
            self.api.hass, self.async_update, self._attr_update_interval
        )

    async def async_added_to_hass(self) -> None:
        """Register callbacks for handling update events."""

        @callback
        def handle_event(event: Event):
            if event.event_type == str(self.device_id):
                if event.data["feedback_type"] == "weather_feedback":
                    #     """
                    #             "wind": wind_direction,
                    #             "temperature": temperature,
                    #             "humidity": humidity,
                    #             "wind_speed": wind_speed,
                    #             "gust_speed": gust_speed,
                    #             "rainfall": rainfall,
                    #             "lighting": lighting,
                    #             "uv": uv,"""
                    # update attributes
                    self._attr_uv_index = float(event.data["uv"])
                    self._attr_native_temperature = event.data["temperature"]
                    logging.error("event data %s", event.data)
            self.schedule_update_ha_state()

        self.listener = self.hass.bus.async_listen(MATCH_ALL, handle_event)

    async def async_will_remove_from_hass(self) -> None:
        """Remove the listener when the entity is removed."""
        self.listener = None

    # send update packet to get initial state

    async def async_update(self, *args, **kwargs) -> None:
        """Get the latest data from Buienradar."""
        await self.api.protocol.sender.send_packet(self.update_packet)

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "TIS Weather Station"

    @property
    def wind_bearing(self) -> float | None:
        """Return the wind direction in degrees from the north pole."""
        return self._attr_wind_bearing

    @property
    def native_temperature(self) -> float | None:
        """Return the temperature."""
        return self._attr_native_temperature

    # TODO: Implement the following method
    @property
    def native_temperature_unit(self) -> str:
        """Return the unit of measurement."""
        return UnitOfTemperature.CELSIUS

    @property
    def humidity(self) -> float | None:
        """Return the humidity."""
        return self._attr_humidity

    @property
    def native_wind_speed(self) -> float | None:
        """Return the wind speed."""
        return self._attr_native_wind_speed

    @property
    def native_wind_gust_speed(self) -> float | None:
        """Return the wind gust speed."""
        return self._attr_native_wind_gust_speed

    @property
    def uv_index(self) -> float | None:
        """Return the UV index."""
        return self._attr_uv_index

    # TODO: Implement the following method
    @property
    def condition(self) -> str | None:
        """Return the current condition."""
        return self._attr_condition
