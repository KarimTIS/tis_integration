from homeassistant.components.select import SelectEntity, ATTR_OPTIONS
from TISControlProtocol.mock_api import TISApi
from .const import DOMAIN
from homeassistant.const import MATCH_ALL
from homeassistant.core import callback, Event, HomeAssistant
from TISControlProtocol.Protocols.udp.ProtocolHandler import (
    TISPacket,
    TISProtocolHandler,
)
import logging

SECURITY_OPTIONS = {"vacation": 1, "away": 2, "night": 3, "disarm": 6}
SECURITY_FEEDBACK_OPTIONS = {1: "vacation", 2: "away", 3: "night", 6: "disarm"}

handler = TISProtocolHandler()

async def async_setup_entry(hass: HomeAssistant, entry, async_add_devices):
    """Set up the TIS switches."""
    tis_api: TISApi = entry.runtime_data.api
    # # Fetch all switches from the TIS API
    # await tis_api.get_entities()
    # switches: dict = tis_api._config_entries.get("switch", None)
    # if switches:
    #     # Prepare a list of tuples containing necessary switch details
    #     switch_entities = [
    #         (
    #             appliance_name,
    #             next(iter(appliance["channels"][0].values())),
    #             appliance["device_id"],
    #         )
    #         for switch in switches
    #         for appliance_name, appliance in switch.items()
    #     ]
    #     # Create TISSwitch objects and add them to Home Assistant
    #     tis_switches = [
    #         TISSwitch(tis_api, switch_name, channel_number, device_id)
    #         for switch_name, channel_number, device_id in switch_entities
    #     ]
    #     async_add_devices(tis_switches)



    async_add_devices(
        [
            TISSecurity(
                name="Security Module",
                api=tis_api,
                options=list(SECURITY_OPTIONS.keys()),
                initial_option="disarm",
                channel_number= 1,
                device_id=[1,10],
                gateway = "192.168.100.200"
            )
        ]
    )


class TISSecurity(SelectEntity):
    def __init__(self, api, name, options, initial_option, channel_number, device_id, gateway):
        self._name = name
        self.api = api
        self._attr_options = options
        self._attr_current_option = initial_option
        self._attr_icon = "mdi:shield"
        self._attr_is_protected = True
        self._attr_read_only = True
        self._listner = None
        self.channel_number=int(channel_number)
        self.device_id = device_id
        self.gateway = gateway

    async def async_added_to_hass(self) -> None:
        @callback
        async def handle_event(event: Event):
            """Handle a admin lock status change event."""
            self.protect() if event.data.get("locked") else self.unprotect()

            if event.data.get("feedback_type") == "security_feedback":
                if self.channel_number == event.data["channel_number"]:
                    mode = event.data["mode"]
                    if mode in SECURITY_FEEDBACK_OPTIONS:
                        option = SECURITY_FEEDBACK_OPTIONS[mode]
                        self._state = self._attr_current_option = option

            self.async_write_ha_state()

            # self.update_security_status()

        self._listener = self.hass.bus.async_listen(MATCH_ALL, handle_event)


    @property
    def name(self):
        return self._name

    @property
    def options(self):
        return self._attr_options

    @property
    def current_option(self):
        return self._attr_current_option

    def protect(self):
        self._attr_read_only = True

    def unprotect(self):
        self._attr_read_only = False

    async def async_select_option(self, option):
        if self._attr_is_protected:
            if self._attr_read_only:
                # revert state to the current option
                raise ValueError("The security module is protected and read only")

        if option not in self._attr_options:
            raise ValueError(
                f"Invalid option: {option} (possible options: {self._attr_options})"
            )
        mode = SECURITY_OPTIONS.get(option,None)
        if mode:
            control_packet = handler.generate_control_security_packet(self,mode)
            logging.error(f"Security packet: {control_packet}")
            ack = await self.api.protocol.sender.send_packet_with_ack(control_packet)
            
            if ack:
                # set state        
                self._state = self._attr_current_option = option
                self.async_write_ha_state()



# type: ignore
