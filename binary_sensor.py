"""Binary sensor Platform."""

from __future__ import annotations
import logging

from TISControlProtocol.api import TISApi

from homeassistant.components.binary_sensor import (
    STATE_OFF,
    STATE_ON,
    BinarySensorEntity,
)
from homeassistant.const import MATCH_ALL
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TISConfigEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: TISConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the TIS binary sensors."""
    tis_api: TISApi = entry.runtime_data.api
    # Fetch all switches from the TIS API
    binary_sensors: dict = await tis_api.get_entities(platform="binary_sensor")
    if binary_sensors:
        sensor_entities = [
            (
                appliance_name,
                next(iter(appliance["channels"][0].values())),
                appliance["device_id"],
                appliance["gateway"],
                appliance["is_protected"],
            )
            for sensor in binary_sensors
            for appliance_name, appliance in sensor.items()
        ]
        tis_sensors = [
            TISBinarySensor(
                tis_api=tis_api,
                sensor_name=sensor_name,
                channel_number=channel_number,
                device_id=device_id,
                gateway=gateway,
            )
            for sensor_name, channel_number, device_id, gateway, is_protected in sensor_entities
        ]

    async_add_entities(tis_sensors)


class TISBinarySensor(BinarySensorEntity):
    """Representation of a TIS binary sensor."""

    def __init__(
        self,
        tis_api: TISApi,
        sensor_name,
        channel_number,
        device_id: list[int],
        gateway: str,
        device_class: str="motion",
    ):
        """Initialize the sensor."""
        self._api = tis_api
        self._name = sensor_name
        self._device_id = device_id
        self._channel_number = int(channel_number)
        self._listener = None
        self._attr_state = None
        self._attr_is_on = None
        self._attr_device_class = (device_class,)
        self._gateway = gateway
        self._attr_unique_id = f"{self._name}_{self._channel_number}"

    async def async_added_to_hass(self):
        @callback
        async def handle_event(event: Event):
            """Handle the event."""
            if event.event_type == str(self._device_id):
                if event.data["feedback_type"] == "auto_binary_feedback":
                    channel_value = event.data["channels_values"][
                        self._channel_number - 1
                    ]
                    if int(channel_value) == 1:
                        self._attr_is_on = True
                        self._attr_state = STATE_ON
                    else:
                        self._attr_is_on = False
                        self._attr_state = STATE_OFF

                elif event.data["feedback_type"] == "realtime_feedback":
                    if event.data["channel_number"] == self._channel_number:
                        updated_channel_value = int(event.data["additional_bytes"][1])
                        if updated_channel_value == 100:
                            self._attr_is_on = True
                            self._attr_state = STATE_ON
                        else:
                            self._attr_is_on = False
                            self._attr_state = STATE_OFF

                        logging.error(
                            f"got real time up[date for {self._channel_number}, value: {updated_channel_value}"
                        )

            await self.async_update_ha_state(True)

        self._listener = self.hass.bus.async_listen(MATCH_ALL, handle_event)

    async def async_will_remove_from_hass(self):
        """Remove the listener when the entity is removed."""
        self._listener()
        self._listener = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def is_on(self):
        """Return the state of the sensor."""
        return self._attr_is_on
