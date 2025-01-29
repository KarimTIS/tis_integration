"""Base class for all entities using the DataUpdateCoordinator."""

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)


class BaseSensorEntity(CoordinatorEntity):
    """Base class for all entities using the DataUpdateCoordinator."""

    def __init__(self, coordinator, name: str, device_id: list) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.coordinator: DataUpdateCoordinator = coordinator
        self._attr_name: str = name
        self._state = None
        self._device_id: list = device_id

    async def async_added_to_hass(self) -> None:
        """Register for updates from the coordinator."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_state(self.coordinator.data)
        self.async_write_ha_state()

    def _update_state(self, data):
        """Update the state based on the data."""
        raise NotImplementedError

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def state(self):
        """Return the current state."""
        return self._state
