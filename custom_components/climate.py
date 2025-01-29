"""Climate platform for integration_blueprint."""

from __future__ import annotations

import logging
from typing import Any

from TISControlProtocol.api import TISApi
from TISControlProtocol.Protocols.udp.ProtocolHandler import (
    TISPacket,
    TISProtocolHandler,
)

from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    UnitOfTemperature,
)
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TISConfigEntry
from .const import FAN_MODES, TEMPERATURE_RANGES

handler = TISProtocolHandler()


async def async_setup_entry(
    hass: HomeAssistant, entry: TISConfigEntry, async_add_devices: AddEntitiesCallback
) -> None:
    """Set up the climate platform."""
    tis_api: TISApi = entry.runtime_data.api
    # Fetch all ACs from the TIS API
    acs: list[dict] = await tis_api.get_entities(platform="ac")
    if acs:
        # Prepare a list of tuples containing necessary ac details
        ac_entities = [
            (
                appliance_name,
                next(iter(appliance["channels"][0].values())),
                appliance["device_id"],
                appliance["is_protected"],
                appliance["gateway"],
            )
            for ac in acs
            for appliance_name, appliance in ac.items()
        ]
        # Create TISClimate objects and add them to Home Assistant
        tis_acs = [
            TISClimate(
                tis_api=tis_api,
                ac_name=ac_name,
                ac_number=ac_number,
                device_id=device_id,
                gateway=gateway,
            )
            for ac_name, ac_number, device_id, is_protected, gateway in ac_entities
        ]
        # add your acs here
        async_add_devices(tis_acs)

    # Fetch all floor heating from the TIS API
    heaters: list[dict] = await tis_api.get_entities(platform="floor_heating")
    if heaters:
        # Prepare a list of tuples containing necessary heater details
        heater_entities = [
            (
                appliance_name,
                next(iter(appliance["channels"][0].values())),
                appliance["device_id"],
                appliance["is_protected"],
                appliance["gateway"],
            )
            for heater in heaters
            for appliance_name, appliance in heater.items()
        ]
        # Create TISFloorHeating objects and add them to Home Assistant
        tis_heaters = [
            TISFloorHeating(
                tis_api=tis_api,
                heater_name=heater_name,
                heater_number=heater_number,
                device_id=device_id,
                gateway=gateway,
            )
            for heater_name, heater_number, device_id, is_protected, gateway in heater_entities
        ]
        async_add_devices(tis_heaters)


class TISClimate(ClimateEntity):
    """Representation of a climate entity."""

    def __init__(
        self,
        tis_api: TISApi,
        ac_name,
        ac_number,
        device_id: list[int],
        gateway: str,
    ) -> None:
        """Initialize the climate entity."""
        self.api = tis_api
        self._name = ac_name
        self.device_id = device_id
        self.ac_number = int(ac_number) - 1
        self._attr_unique_id = f"ac_{self.device_id}_{self.ac_number}"
        self.gateway = gateway
        self._attr_temperature_unit: UnitOfTemperature = UnitOfTemperature.CELSIUS
        self._unit_index = (
            0 if self._attr_temperature_unit == UnitOfTemperature.CELSIUS else 1
        )
        # initialize all required attributes for the climate entity
        self.update_packet: TISPacket = handler.generate_ac_update_packet(self)
        self.listener = None
        self._attr_state = STATE_OFF
        self._attr_target_temperature = None
        self._attr_current_temperature = None
        self._attr_max_temp = None
        self._attr_min_temp = None
        self._attr_target_temperature_step = None
        self.setup_ac()

    def setup_ac(self):
        """Set up the AC."""
        self._attr_hvac_mode = HVACMode.COOL
        self._attr_fan_mode = FAN_MEDIUM
        self._attr_max_temp = TEMPERATURE_RANGES[self._attr_hvac_mode]["max"][
            self._unit_index
        ]
        self._attr_min_temp = TEMPERATURE_RANGES[self._attr_hvac_mode]["min"][
            self._unit_index
        ]
        self._attr_target_temperature = TEMPERATURE_RANGES[self._attr_hvac_mode][
            "target"
        ][self._unit_index]
        self._attr_target_temperature_step = 1 if self._unit_index == 0 else 2
        self._attr_hvac_modes = [
            HVACMode.OFF,
            HVACMode.HEAT,
            HVACMode.COOL,
            HVACMode.AUTO,
            HVACMode.FAN_ONLY,
        ]
        self._attr_supported_features = (
            ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
        )
        self._attr_fan_modes = [
            FAN_AUTO,
            FAN_LOW,
            FAN_MEDIUM,
            FAN_HIGH,
        ]
        self.mode_target_temperatures = {
            HVACMode.COOL: 20,
            HVACMode.HEAT: 30,
            HVACMode.FAN_ONLY: None,
            HVACMode.AUTO: 20,
            HVACMode.OFF: None,
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to events."""

        @callback
        async def handle_event(event: Event):
            """Handle the event."""
            if event.event_type == str(self.device_id):
                feedback_type = event.data.get("feedback_type", None)
                if feedback_type == "ac_feedback":
                    ac_number = event.data["number"]
                    sub_operation = event.data["sub_operation"]
                    operation_value = event.data["operation_value"]

                    if self.ac_number == int(ac_number):
                        logging.warning("AC feedback event: %s", event.data)
                        if sub_operation == 0x03:
                            if operation_value == 0x00:
                                # Turn off
                                self._attr_state = STATE_OFF
                                self._attr_hvac_mode = HVACMode.OFF
                                logging.info("AC turned off")
                        else:
                            self._attr_state = STATE_ON
                            if sub_operation == 0x04:
                                # Update cool mode temperature
                                self._attr_hvac_mode = HVACMode.COOL
                                self._attr_target_temperature = operation_value
                                self._attr_current_temperature = operation_value
                                logging.info(
                                    "Cool mode temperature updated to %s",
                                    operation_value,
                                )
                            elif sub_operation == 0x05:
                                # Update fan speed
                                self._attr_fan_mode = next(
                                    key
                                    for key, value in FAN_MODES.items()
                                    if value == operation_value
                                )
                                logging.info("Fan speed updated to %s", operation_value)
                            elif sub_operation == 0x06:
                                # Change HVAC mode
                                self._attr_hvac_mode = next(
                                    (
                                        hvac_mode
                                        for hvac_mode, settings in TEMPERATURE_RANGES.items()
                                        if settings["packet_mode_index"]
                                        == operation_value
                                    ),
                                    None,
                                )
                                logging.info("HVAC mode changed to %s", operation_value)
                            elif sub_operation == 0x07:
                                # Update heating mode temperature
                                self._attr_hvac_mode = HVACMode.HEAT
                                self._attr_target_temperature = operation_value
                                self._attr_current_temperature = operation_value
                                logging.info(
                                    "Heating mode temperature updated to %s",
                                    operation_value,
                                )

                            elif sub_operation == 0x08:
                                # Update Auto mode temperature
                                self._attr_hvac_mode = HVACMode.AUTO
                                self._attr_target_temperature = operation_value
                                self._attr_current_temperature = operation_value
                                logging.info(
                                    "Auto mode temperature updated to %s",
                                    operation_value,
                                )

                            else:
                                logging.error(
                                    "Unknown sub operation for AC feedback: %s",
                                    sub_operation,
                                )
                elif feedback_type == "update_feedback":
                    if event.data["ac_number"] == self.ac_number:
                        if event.data["state"] == 0x00:
                            # turn off
                            self._attr_state = STATE_OFF
                            self._attr_hvac_mode = HVACMode.OFF
                        else:
                            self._attr_state = STATE_ON
                            self._attr_hvac_mode = next(
                                (
                                    hvac_mode
                                    for hvac_mode, settings in TEMPERATURE_RANGES.items()
                                    if settings["packet_mode_index"]
                                    == event.data["hvac_mode"]
                                ),
                                None,
                            )
                            self._attr_fan_mode = next(
                                key
                                for key, value in FAN_MODES.items()
                                if value == event.data["fan_speed"]
                            )
                            # set temperature rangs
                            self._attr_min_temp = TEMPERATURE_RANGES[self.hvac_mode][
                                "min"
                            ][self._unit_index]
                            self._attr_max_temp = TEMPERATURE_RANGES[self.hvac_mode][
                                "max"
                            ][self._unit_index]
                            # setting temperature based on mode
                            if self._attr_hvac_mode == HVACMode.COOL:
                                self._attr_target_temperature = event.data["cool_temp"]
                            elif self._attr_hvac_mode == HVACMode.HEAT:
                                self._attr_target_temperature = event.data["heat_temp"]
                            elif self._attr_hvac_mode == HVACMode.AUTO:
                                self._attr_target_temperature = event.data["auto_temp"]
                            else:
                                self._attr_target_temperature = None
            self.async_write_ha_state()
            await self.async_update_ha_state(True)

        self.listener = self.hass.bus.async_listen(str(self.device_id), handle_event)
        await self.api.protocol.sender.send_packet(self.update_packet)

    # getters
    @property
    def name(self) -> str:
        """Return the name of the climate entity."""
        return self._name

    @property
    def is_on(self) -> bool:
        """Return the state of the switch."""
        if self._attr_state == STATE_ON:
            return True

        elif self._attr_state == STATE_OFF:
            return False

        else:
            return None

    @property
    def temperature_unit(self) -> UnitOfTemperature:
        """Return the unit of measurement."""
        return self._attr_temperature_unit

    @property
    def current_temperature(self) -> float:
        """Return the current temperature."""
        return self._attr_target_temperature

    @property
    def target_temperature(self) -> float:
        """Return the temperature we try to reach."""
        return self._attr_target_temperature

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current operation."""
        return self._attr_hvac_mode

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the list of available operation modes."""
        return self._attr_hvac_modes

    @property
    def fan_modes(self) -> list[str]:
        """Return the fan setting."""
        return self._attr_fan_modes

    @property
    def should_poll(self) -> bool:
        """Return False if entity pushes its state to HA."""
        return False

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode and store changes only after the packet is sent."""
        # Determine the new state based on the HVAC mode
        if hvac_mode == HVACMode.OFF:
            new_state = STATE_OFF
            new_target_temperature = None
            new_min_temp = None
            new_max_temp = None
        else:
            new_state = STATE_ON
            # Determine the new temperature ranges and target temperature
            new_min_temp = TEMPERATURE_RANGES[hvac_mode]["min"][self._unit_index]
            new_max_temp = TEMPERATURE_RANGES[hvac_mode]["max"][self._unit_index]
            new_target_temperature = self.mode_target_temperatures[hvac_mode]

        # Generate the packet with the new values
        packet = handler.generate_ac_control_packet(
            self,
            TEMPERATURE_RANGES,
            FAN_MODES,
            target_state=new_state,
            target_temperature=new_target_temperature,
            target_mode=hvac_mode,
        )

        # Send the packet and check for acknowledgment
        ack_stats = await self.api.protocol.sender.send_packet_with_ack(packet)
        if ack_stats:
            # Update the class attributes only if the packet is acknowledged
            self._attr_hvac_mode = hvac_mode
            self._attr_state = new_state
            self._attr_min_temp = new_min_temp
            self._attr_max_temp = new_max_temp
            self._attr_current_temperature = self._attr_target_temperature = (
                new_target_temperature
            )
        else:
            logging.error("Failed to set hvac mode")
            self._attr_state = STATE_UNKNOWN
            self._attr_hvac_mode = None
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """."""
        packet = handler.generate_ac_control_packet(
            self,
            TEMPERATURE_RANGES,
            FAN_MODES,
            target_fan_mode=fan_mode,
        )
        ack_stats = await self.api.protocol.sender.send_packet_with_ack(packet)
        if ack_stats:
            self._attr_fan_mode = fan_mode
        else:
            logging.error("Failed to set fan mode")
            self._attr_state = STATE_UNKNOWN
            self._attr_fan_mode = None
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        new_target_temperature = kwargs.get(ATTR_TEMPERATURE)

        packet = handler.generate_ac_control_packet(
            self,
            TEMPERATURE_RANGES,
            FAN_MODES,
            target_temperature=new_target_temperature,
        )
        ack_status = await self.api.protocol.sender.send_packet_with_ack(packet)
        if ack_status:
            self._attr_current_temperature = self._attr_target_temperature = (
                new_target_temperature
            )
            # update temperature holders
            self.mode_target_temperatures[self.hvac_mode] = (
                new_target_temperature
                if new_target_temperature
                else self.target_temperature
            )
        else:
            self._attr_state = STATE_UNKNOWN
            logging.error("Failed to set temperature")
            self._attr_target_temperature = None
            self._attr_hvac_mode = None
            self._attr_current_temperature = None
        self.async_write_ha_state()


class TISFloorHeating(ClimateEntity):
    """Representation of a climate entity."""

    def __init__(
        self,
        tis_api: TISApi,
        heater_name,
        heater_number,
        device_id: list[int],
        gateway: str,
    ) -> None:
        """Initialize the climate entity."""
        self.api = tis_api
        self._name = heater_name
        self.device_id = device_id
        self.heater_number = int(heater_number) - 1
        self._attr_unique_id = f"floor_heater_{self.device_id}_{self.heater_number}"
        self.gateway = gateway
        self._attr_temperature_unit: UnitOfTemperature = UnitOfTemperature.CELSIUS
        self._unit_index = (
            0 if self._attr_temperature_unit == UnitOfTemperature.CELSIUS else 1
        )
        # initialize all required attributes for the climate entity
        self.update_packet: TISPacket = handler.generate_floor_update_packet(self)
        self.listener = None
        self._attr_state = STATE_OFF
        self._attr_target_temperature = None
        self._attr_current_temperature = None
        self._attr_max_temp = None
        self._attr_min_temp = None
        self._attr_target_temperature_step = None
        self.setup_heater()

    def setup_heater(self):
        """Set up the AC."""
        self._attr_hvac_mode = HVACMode.HEAT
        self._attr_max_temp = TEMPERATURE_RANGES[self._attr_hvac_mode]["max"][
            self._unit_index
        ]
        self._attr_min_temp = TEMPERATURE_RANGES[self._attr_hvac_mode]["min"][
            self._unit_index
        ]
        self._attr_target_temperature = TEMPERATURE_RANGES[self._attr_hvac_mode][
            "target"
        ][self._unit_index]
        self._attr_target_temperature_step = 1 if self._unit_index == 0 else 2
        self._attr_hvac_modes = [
            HVACMode.OFF,
            HVACMode.HEAT,
        ]
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
        )
        self.mode_target_temperatures = {
            HVACMode.HEAT: 30,
            HVACMode.OFF: None,
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to events."""

        @callback
        async def handle_event(event: Event):
            """Handle the event."""
            if event.event_type == str(self.device_id):
                feedback_type = event.data.get("feedback_type", None)
                if feedback_type == "floor_feedback":
                    logging.warning("floor heating feedback event: %s", event.data)
                    heater_number = event.data["number"]
                    sub_operation = event.data["sub_operation"]
                    operation_value = event.data["operation_value"]

                    if self.heater_number == int(heater_number):
                        if sub_operation == 0x14:
                            if operation_value == 0x00:
                                # Turn off
                                self._attr_state = STATE_OFF
                                self._attr_hvac_mode = HVACMode.OFF
                                logging.info("Heater turned off")
                            else:
                                self._attr_state = STATE_ON
                                self._attr_hvac_mode = HVACMode.HEAT
                                self._attr_target_temperature = operation_value
                                self._attr_current_temperature = operation_value
                                logging.info(
                                    "Heating mode temperature updated to %s",
                                    operation_value,
                                )
                        elif sub_operation == 0x18:
                            # set temperature
                            self._attr_target_temperature = operation_value
                            self._attr_current_temperature = operation_value
                        else:
                            logging.error(
                                "Unknown sub operation for AC feedback: %s",
                                sub_operation,
                            )
                elif feedback_type == "floor_update":
                    logging.warning("floor heating update event: %s", event.data)
                    if event.data["heater_number"] == self.heater_number:
                        if event.data["state"] == 0x00:
                            # turn off
                            self._attr_state = STATE_OFF
                            self._attr_hvac_mode = HVACMode.OFF
                        else:
                            self._attr_state = STATE_ON
                            self._attr_hvac_mode = HVACMode.HEAT
                            # set temperature rangs
                            self._attr_min_temp = TEMPERATURE_RANGES[self.hvac_mode][
                                "min"
                            ][self._unit_index]
                            self._attr_max_temp = TEMPERATURE_RANGES[self.hvac_mode][
                                "max"
                            ][self._unit_index]
                            # setting temperature based on mode
                            if self._attr_hvac_mode == HVACMode.HEAT:
                                self._attr_target_temperature = event.data["temp"]
                            else:
                                self._attr_target_temperature = None
            self.async_write_ha_state()
            await self.async_update_ha_state(True)

        self.listener = self.hass.bus.async_listen(str(self.device_id), handle_event)
        await self.api.protocol.sender.send_packet(self.update_packet)

    # getters
    @property
    def name(self) -> str:
        """Return the name of the climate entity."""
        return self._name

    @property
    def is_on(self) -> bool:
        """Return the state of the entity."""
        if self._attr_state == STATE_ON:
            return True
        elif self._attr_state == STATE_OFF:
            return False
        else:
            return None

    @property
    def temperature_unit(self) -> UnitOfTemperature:
        """Return the unit of measurement."""
        return self._attr_temperature_unit

    @property
    def current_temperature(self) -> float:
        """Return the current temperature."""
        return self._attr_target_temperature

    @property
    def target_temperature(self) -> float:
        """Return the temperature we try to reach."""
        return self._attr_target_temperature

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current operation."""
        return self._attr_hvac_mode

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the list of available operation modes."""
        return self._attr_hvac_modes

    @property
    def should_poll(self) -> bool:
        """Return False if entity pushes its state to HA."""
        return False

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode and store changes only after the packet is sent."""
        packet = handler.generate_floor_on_off_packet(
            self, 0x00 if hvac_mode == HVACMode.OFF else 0x01
        )
        await self.api.protocol.sender.send_packet(packet)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        new_target_temperature = kwargs.get(ATTR_TEMPERATURE)
        packet = handler.generate_floor_on_off_packet(
            self, 0x00 if self._attr_state == STATE_OFF else 0x01
        )
        await self.api.protocol.sender.send_packet(packet)
        packet = handler.generate_floor_set_temp_packet(
            self, int(new_target_temperature)
        )
        await self.api.protocol.sender.send_packet_with_ack(packet)
