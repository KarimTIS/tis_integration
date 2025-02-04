"""Fan platform for TIS Control."""

from __future__ import annotations
from typing import Any
import logging

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from TISControlProtocol.api import TISApi

from . import TISConfigEntry
import RPi.GPIO as GPIO

SUPPORT = (
    FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_OFF | FanEntityFeature.TURN_ON
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: TISConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TIS Control Fans."""
    tis_api: TISApi = entry.runtime_data.api
    async_add_entities(
        [
            TISCPUFan(
                hass,
                "CPU_Fan",
                "CPU Fan Speed Controller",
                SUPPORT,
                tis_api,
            )
        ]
    )


class TISCPUFan(FanEntity):
    """A platform to control CPU fan from RPI GPIO."""

    _attr_should_poll = False
    _attr_translation_key = "cpu"

    def __init__(
        self,
        hass: HomeAssistant,
        unique_id: str,
        name: str,
        supported_features: FanEntityFeature,
        api: TISApi,
        pin: int = 13,
        lower_threshold: float = 40,
        higher_threshold: float = 50
    ) -> None:
        """Initialize the entity."""
        self._pin = pin
        self._state = True
        self._higher_temperature_threshold = higher_threshold
        self._lower_temperature_threshold = lower_threshold
        self._listener = None
        self._api = api
        self.hass = hass
        self._unique_id = unique_id
        self._attr_supported_features = supported_features
        self._percentage: int | None = None
        self._attr_name = name

        if supported_features & FanEntityFeature.OSCILLATE:
            self._oscillating = False
        if supported_features & FanEntityFeature.DIRECTION:
            self._direction = "forward"

        self.setup_light()

    def setup_light(self):
        # Set up the GPIO pin
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self._pin, GPIO.OUT)
            self._pwm = GPIO.PWM(self._pin, 100)  # 100Hz frequency
            self._pwm.start(50)  # Start with duty cycle of 50%
        except RuntimeError:
            logging.error("GPIO PWM already in use")
            self._pwm = None
            self._attr_available = False

    async def async_added_to_hass(self):
        @callback
        async def handle_overheat_event(event: Event):
            """Handle the event."""
            try:
                temp = event.data.get("temperature")
                if temp is None:
                    return

                if temp > self._higher_temperature_threshold:
                    await self.async_turn_on(percentage=100)
                elif temp > self._lower_temperature_threshold:
                    await self.async_turn_on(percentage=50)
                else:
                    await self.async_turn_on(percentage=25)
            except Exception as e:
                logging.error(f"Error adjusting fan speed: {e}")


        self._listener = self.hass.bus.async_listen(
            "cpu_temperature", handle_overheat_event
        )

    @property
    def name(self):
        return self._attr_name

    @property
    def icon(self):
        """Return the icon to use in the frontend, if any."""
        return "mdi:fan"

    @property
    def is_on(self):
        """Return true if the fan is on."""
        return self._state

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return self._unique_id

    @property
    def percentage(self) -> int | None:
        """Return the current speed."""
        return self._percentage

    def log_fan_state(self):
        """Log current fan state for debugging."""
        logging.info(
            f"Fan State - "
            f"Percentage: {self._percentage}, "
            f"Temperature Range: {self._lower_temperature_threshold}-{self._higher_temperature_threshold}"
        )

    @property
    def supported_features(self):
        return self._attr_supported_features

    async def async_will_remove_from_hass(self) -> None:
        """Disconnect PWM when removed."""
        if self._listener:
            self._listener()
    
        if self._pwm:
            try:
                self._pwm.stop()
                GPIO.cleanup(self._pin)
            except Exception as e:
                logging.error(f"Error cleaning up GPIO: {e}")

    async def async_set_percentage(self, percentage: int) -> None:
        """Set the speed of the fan, as a percentage."""
        self._percentage = percentage
        self._pwm.ChangeDutyCycle(self._percentage)
        self._state = True
        self.async_write_ha_state()

    async def async_turn_on(
        self,
        percentage: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn the fan on."""
        if percentage is None:
            percentage = 50
        await self.async_set_percentage(percentage)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the fan off."""
        self._pwm.ChangeDutyCycle(0)
        self._state = False
        self.async_write_ha_state()