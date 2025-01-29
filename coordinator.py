"""Define a generic data update coordinator."""

from datetime import timedelta
import logging

from TISControlProtocol.api import TISApi
from TISControlProtocol.Protocols.udp.ProtocolHandler import (
    TISPacket,
    TISProtocolHandler,
)

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)
HANDLER = TISProtocolHandler()


class SensorUpdateCoordinator(DataUpdateCoordinator):
    """Define a sensor data update coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: TISApi,
        update_interval: timedelta,
        device_id: list[int, int],
        update_packet: TISPacket,
    ) -> None:
        """Initialize the coordinator."""
        self.api = api
        self.device_id = device_id
        self.update_packet = update_packet
        super().__init__(
            hass,
            _LOGGER,
            name=f"Sensor Update Coordinator for {device_id}",
            update_interval=timedelta(seconds=30),
        )

    async def _async_update_data(self) -> bool:
        """Fetch data from API."""
        # Here you should return the data fetched from the API
        logging.error(f"Update New async update date: {self.update_packet}")
        return await self.api.protocol.sender.send_packet(self.update_packet)
