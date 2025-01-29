"""Cover platform fot TIS Control."""

import logging
from math import ceil
from typing import Any

from TISControlProtocol.api import TISApi
from TISControlProtocol.BytesHelper import int_to_8_bit_binary
from TISControlProtocol.Protocols.udp.ProtocolHandler import (
    TISPacket,
    TISProtocolHandler,
)

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.const import STATE_CLOSING, STATE_OPENING, STATE_UNKNOWN, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TISConfigEntry

handler = TISProtocolHandler()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TISConfigEntry,
    async_add_devices: AddEntitiesCallback,
) -> None:
    """Set up TIS Control lights."""
    tis_api: TISApi = entry.runtime_data.api
    # Fetch all covers from the TIS API
    covers_w_pos: dict = await tis_api.get_entities(platform="motor")
    covers: dict = await tis_api.get_entities(platform="shutter")

    if covers_w_pos:
        # Prepare a list of tuples containing necessary cover details
        cover_entities = [
            (
                cover_name,
                next(iter(cover["channels"][0].values())),
                cover["device_id"],
                cover["gateway"],
            )
            for cover in covers_w_pos
            for cover_name, cover in cover.items()
        ]
        # Create TISCover objects and add them to Home Assistant
        tis_covers = [
            TISCoverWPos(
                tis_api=tis_api,
                cover_name=cover_name,
                channel_number=channel_number,
                device_id=device_id,
                gateway=gateway,
            )
            for cover_name, channel_number, device_id, gateway in cover_entities
        ]
        async_add_devices(tis_covers, update_before_add=True)

    if covers:
        # Prepare a list of tuples containing necessary cover details
        cover_entities = [
            (
                cover_name,
                next(iter(cover["channels"][0].values())),
                next(iter(cover["channels"][1].values())),
                cover["device_id"],
                cover["gateway"],
            )
            for cover in covers
            for cover_name, cover in cover.items()
        ]
        # Create TISCover objects and add them to Home Assistant
        tis_covers = [
            TISCoverNoPos(
                tis_api=tis_api,
                cover_name=cover_name,
                up_channel_number=up_channel_number,
                down_channel_number=down_channel_number,
                device_id=device_id,
                gateway=gateway,
            )
            for cover_name, up_channel_number, down_channel_number, device_id, gateway in cover_entities
        ]
        async_add_devices(tis_covers, update_before_add=True)


class TISCoverWPos(CoverEntity):
    """Representation of a TIS cover with position feedback."""

    def __init__(
        self,
        tis_api: TISApi,
        gateway: str,
        cover_name: str,
        channel_number: int,
        device_id: list[int],
    ) -> None:
        """Initialize the cover."""
        self.api = tis_api
        self.gateway = gateway
        self.device_id = device_id
        self.channel_number = int(channel_number)
        self._attr_name = cover_name
        self._attr_is_closed = None
        self._attr_current_cover_position = None
        self._attr_device_class = CoverDeviceClass.SHUTTER
        self._attr_unique_id = f"{self._attr_name}_{self.channel_number}"
        self.listener = None
        ##############################################
        self.update_packet: TISPacket = handler.generate_control_update_packet(self)
        self.generate_cover_packet = handler.generate_light_control_packet

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""

        @callback
        async def handle_event(event: Event):
            """Handle the event."""
            # check if event is for this switch
            if event.event_type == str(self.device_id):
                if event.data["feedback_type"] == "control_response":
                    logging.warning("channel number for cover: %s", self.channel_number)
                    channel_value = event.data["additional_bytes"][2]
                    channel_number = event.data["channel_number"]
                    if int(channel_number) == self.channel_number:
                        self._attr_is_closed = channel_value == 0
                        self._attr_current_cover_position = channel_value
                    self.async_write_ha_state()
                elif event.data["feedback_type"] == "binary_feedback":
                    n_bytes = ceil(event.data["additional_bytes"][0] / 8)
                    channels_status = "".join(
                        int_to_8_bit_binary(event.data["additional_bytes"][i])
                        for i in range(1, n_bytes + 1)
                    )
                    if channels_status[self.channel_number - 1] == "0":
                        self._attr_is_closed = True
                    self.async_write_ha_state()
                elif event.data["feedback_type"] == "update_response":
                    additional_bytes = event.data["additional_bytes"]
                    self._attr_current_cover_position = additional_bytes[
                        self.channel_number
                    ]
                    self._attr_is_closed = self._attr_current_cover_position == 0
                    self._attr_state = (
                        STATE_CLOSING if self._attr_is_closed else STATE_OPENING
                    )
                elif event.data["feedback_type"] == "offline_device":
                    self._attr_state = STATE_UNKNOWN
                    self._attr_is_closed = None
                    self._attr_current_cover_position = None

            await self.async_update_ha_state(True)

        self.listener = self.hass.bus.async_listen(str(self.device_id), handle_event)
        _ = await self.api.protocol.sender.send_packet(self.update_packet)

    @property
    def name(self) -> str:
        """Return the name of the cover."""
        return self._attr_name

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        return self._attr_is_closed

    @property
    def supported_features(self) -> CoverEntityFeature:
        """Flag supported features."""
        return CoverEntityFeature.SET_POSITION

    @property
    def current_cover_position(self) -> int | None:
        """Return the current position of the cover."""
        return self._attr_current_cover_position

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._attr_unique_id

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        packet = self.generate_cover_packet(self, 100)
        ack_status = await self.api.protocol.sender.send_packet_with_ack(packet)
        if ack_status:
            self._attr_is_closed = False
            self._attr_current_cover_position = 100
        else:
            self._attr_is_closed = None
            self._attr_current_cover_position = None

        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close cover."""
        packet = self.generate_cover_packet(self, 0)
        ack_status = await self.api.protocol.sender.send_packet_with_ack(packet)
        if ack_status:
            self._attr_is_closed = True
            self._attr_current_cover_position = 0
        else:
            self._attr_is_closed = False
            self._attr_current_cover_position = None

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Move the cover to a specific position."""
        packet = self.generate_cover_packet(self, kwargs[ATTR_POSITION])
        ack_status = await self.api.protocol.sender.send_packet_with_ack(packet)
        if ack_status:
            self._attr_is_closed = kwargs[ATTR_POSITION] == 0
            self._attr_current_cover_position = kwargs[ATTR_POSITION]
        else:
            self._attr_is_closed = None
            self._attr_current_cover_position = None


class TISCoverNoPos(CoverEntity):
    """Representation of a TIS cover without position feedback."""

    def __init__(
        self,
        tis_api: TISApi,
        gateway: str,
        cover_name: str,
        up_channel_number: int,
        down_channel_number: int,
        device_id: list[int],
    ) -> None:
        """Initialize the cover."""
        self.api = tis_api
        self.gateway = gateway
        self.device_id = device_id
        self.up_channel_number = int(up_channel_number)
        self.down_channel_number = int(down_channel_number)
        self._attr_name = cover_name
        self._attr_unique_id = (
            f"{self._attr_name}_{self.up_channel_number}_{self.down_channel_number}"
        )
        # for feedback
        self.channel_number = self.up_channel_number
        self._attr_is_closed = None
        self._attr_device_class = CoverDeviceClass.WINDOW
        self.last_status = STATE_OPENING
        self.listener = None
        # self.up_update_packet: TISPacket = handler.generate_control_update_packet(self)
        # self.up_update_packet: TISPacket = handler.generate_control_update_packet(self)

    async def async_added_to_hass(self) -> None:
        """Subscribe to events."""

        @callback
        async def handle_event(event: Event):
            """Handle the event."""
            # check if event is for this switch
            if event.event_type == str(self.device_id):
                if event.data["feedback_type"] == "control_response":
                    channel_value = event.data["additional_bytes"][2]
                    channel_number = event.data["channel_number"]
                    if int(channel_number) == self.up_channel_number:
                        if channel_value != 0:
                            self._attr_is_closed = False
                            self.last_status = STATE_OPENING
                    elif int(channel_number) == self.down_channel_number:
                        if channel_value != 0:
                            self._attr_is_closed = True
                            self.last_status = STATE_CLOSING

                    else:
                        self._attr_is_closed = False if self.last_status == STATE_OPENING else True

                # elif event.data["feedback_type"] == "update_response":
                #     additional_bytes = event.data["additional_bytes"]
                #     channel_status = int(additional_bytes[self.channel_number])
                #     self._state = STATE_ON if channel_status > 0 else STATE_OFF
                # elif event.data["feedback_type"] == "offline_device":
                #     self._state = STATE_UNKNOWN

            await self.async_update_ha_state(True)
            self.schedule_update_ha_state()

        self.listener = self.hass.bus.async_listen(str(self.device_id), handle_event)
        # _ = await self.api.protocol.sender.send_packet(self.update_packet)

    @property
    def name(self) -> str:
        """Return the name of the cover."""
        return self._attr_name

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed."""
        # return self._attr_is_closed
        if self._attr_is_closed == True:
            return True
        elif self._attr_is_closed == False:
            return False
        else: return None

    @property
    def supported_features(self) -> CoverEntityFeature:
        """Flag supported features."""
        return (
            CoverEntityFeature.OPEN | CoverEntityFeature.STOP | CoverEntityFeature.CLOSE
        )

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._attr_unique_id

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        up_packet, down_packet = handler.generate_no_pos_cover_packet(self, "open")
        # we only need to send the up packet here
        ack_status = await self.api.protocol.sender.send_packet_with_ack(up_packet)
        if ack_status:
            self._attr_is_closed = False
            self.last_status = STATE_OPENING
        else:
            self._attr_is_closed = None
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close cover."""
        up_packet, down_packet = handler.generate_no_pos_cover_packet(self, "close")
        # we only need to send the down packet here
        ack_status = await self.api.protocol.sender.send_packet_with_ack(down_packet)
        if ack_status:
            self._attr_is_closed = True
            self.last_status = STATE_CLOSING
        else:
            self._attr_is_closed = None
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        up_packet, down_packet = handler.generate_no_pos_cover_packet(self, "stop")
        # we need to send both packets here
        if self._attr_is_closed:
            ack_status = await self.api.protocol.sender.send_packet_with_ack(
                down_packet
            )
            if ack_status:
                self._attr_state = self.last_status
                self._attr_is_closed = False if self.last_status == STATE_OPENING else True
            else:
                self._attr_state = None
                self._attr_is_closed = None

        elif not self._attr_is_closed:
            ack_status = await self.api.protocol.sender.send_packet_with_ack(up_packet)
            if ack_status:
                self._attr_state = self.last_status
                self._attr_is_closed = False if self.last_status == STATE_OPENING else True
            else:
                self._attr_state = None
                self._attr_is_closed = None
        self.async_write_ha_state()