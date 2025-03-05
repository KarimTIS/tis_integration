from homeassistant.components.select import SelectEntity
from TISControlProtocol.api import TISApi

from homeassistant.const import MATCH_ALL, STATE_UNAVAILABLE
from homeassistant.core import callback, Event, HomeAssistant
from TISControlProtocol.Protocols.udp.ProtocolHandler import (
    TISPacket,
    TISProtocolHandler,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TISConfigEntry

import logging

SECURITY_OPTIONS = {"vacation": 1, "away": 2, "night": 3, "disarm": 6}
SECURITY_FEEDBACK_OPTIONS = {1: "vacation", 2: "away", 3: "night", 6: "disarm"}

handler = TISProtocolHandler()

async def async_setup_entry(hass: HomeAssistant, entry: TISConfigEntry, async_add_devices: AddEntitiesCallback):
    """Set up the TIS select."""
    tis_api: TISApi = entry.runtime_data.api
    # Fetch all switches from the TIS API
    selects: dict = await tis_api.get_entities(platform="security")
    
    if selects:
        # Prepare a list of tuples containing necessary switch details
        select_entities = [
            (
                appliance_name,
                next(iter(appliance["channels"][0].values())),
                appliance["device_id"],
                appliance["gateway"],
            )
            for select in selects
            for appliance_name, appliance in select.items()
        ]
        # Create TISSwitch objects and add them to Home Assistant
        tis_selects = [
            TISSecurity(
                api=tis_api,
                name=select_name,
                options=list(SECURITY_OPTIONS.keys()),
                initial_option="disarm",
                channel_number= channel_number,
                device_id=device_id,
                gateway = gateway
            )
            for select_name, channel_number, device_id, gateway in select_entities
        ]
        async_add_devices(tis_selects)

protocol_handler = TISProtocolHandler()

class TISSecurity(SelectEntity):
    def __init__(self, api, name, options, initial_option, channel_number, device_id, gateway):
        self._name = name
        self.api = api
        self.unique_id = f"select_{self.name}"
        self._attr_options = options
        self._attr_current_option = self._state = initial_option
        self._attr_icon = "mdi:shield"
        self._attr_is_protected = True
        self._attr_read_only = True
        self._listener = None
        self.channel_number=int(channel_number)
        self.device_id = device_id
        self.gateway = gateway
        self.update_packet: TISPacket = protocol_handler.generate_update_security_packet(
            self
        )

    async def async_added_to_hass(self) -> None:
        @callback
        async def handle_event(event: Event):
            """Handle a admin lock status change event."""
            if event.event_type == "admin_lock":
                logging.info(f"admin lock event: {event.data}")
                if event.data.get("locked"):
                    self.protect() 
                else:
                    self.unprotect()

            if event.data.get("feedback_type") == "security_feedback" or event.data.get("feedback_type") == "security_update":
                logging.info(f"security feedback event: {event.data}")
                if self.channel_number == event.data["channel_number"]:
                    mode = event.data["mode"]
                    if mode in SECURITY_FEEDBACK_OPTIONS:
                        option = SECURITY_FEEDBACK_OPTIONS[mode]
                        logging.info(f"mode: {mode}, option: {option}")
                        self._state = self._attr_current_option = option
            self.async_write_ha_state()

        self._listener = self.hass.bus.async_listen(MATCH_ALL, handle_event)
        await self.api.protocol.sender.send_packet(self.update_packet)
        logging.info(f"update packet sent: {self.update_packet}")
        logging.info(f"listener added: {self._listener}")

    @property
    def name(self):
        return self._name

    @property
    def options(self):
        return self._attr_options

    @property
    def current_option(self):
        return self._attr_current_option if self._attr_current_option in SECURITY_FEEDBACK_OPTIONS.values() else None

    def protect(self):
        self._attr_read_only = True

    def unprotect(self):
        self._attr_read_only = False

    async def async_select_option(self, option):
        if self._attr_is_protected:
            if self._attr_read_only:
                # revert state to the current option
                self._state = self._attr_current_option = STATE_UNAVAILABLE
                logging.error("resetting state to last known state")
                await self.api.protocol.sender.send_packet(self.update_packet)
                self.async_write_ha_state()
                raise ValueError("The security module is protected and read only")
            else:
                logging.info(f"setting security mode to {option}")
                mode = SECURITY_OPTIONS.get(option, None)
                if mode:
                    logging.info(f"mode: {mode}")
                    control_packet = handler.generate_control_security_packet(self, mode)
                    ack = await self.api.protocol.sender.send_packet_with_ack(control_packet)
                    logging.info(f"control_packet: {control_packet}")
                    logging.info(f"ack: {ack}")
                    if ack:
                        # set state
                        logging.info(f"setting state to {option}")
                        self._state = self._attr_current_option = option
                        self.async_write_ha_state()
                    else:
                        logging.warning(f"Failed to set security mode to {option}")
                        self._state = self._attr_current_option = None
                        self.async_write_ha_state()

        if option not in self._attr_options:
            raise ValueError(
                f"Invalid option: {option} (possible options: {self._attr_options})"
            )
# type: ignore