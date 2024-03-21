from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.components.test_sensors.const import DOMAIN
from homeassistant.components.test_sensors.coordinator import MyCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Example sensor based on a config entry."""

    my_api = hass.data[DOMAIN][entry.entry_id]
    coordinator = MyCoordinator(hass, my_api)

    #     # Fetch initial data so we have data when entities subscribe
    #     #
    #     # If the refresh fails, async_config_entry_first_refresh will
    #     # raise ConfigEntryNotReady and setup will try again later
    #     #
    #     # If you do not want to retry setup on failure, use
    #     # coordinator.async_refresh() instead
    #     #
    await coordinator.async_config_entry_first_refresh()

    async_add_entities([ExampleSensorEntity(coordinator)])
    # device: ExampleDevice = hass.data[DOMAIN][entry.entry_id]

    # async_add_entities(
    #     ExampleSensorEntity(device, description)
    #     for description in SENSORS
    #     if description.exists_fn(device)
    # )


class ExampleSensorEntity(CoordinatorEntity, SensorEntity):
    """Represent an Example sensor."""

    _attr_has_entity_name = True
    _attr_name = "Test"
    _attr_unique_id = "temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE

    def __init__(self, coordinator: MyCoordinator) -> None:
        """Set up the instance."""
        self.idx = 1
        super().__init__(coordinator, self.idx)
        self.coordinator = coordinator

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.coordinator.data.value
        self.async_write_ha_state()

    # def update(self) -> None:
    #     """Update entity state."""
    #     print("TRIGGERED")
    #     # self._device.update()
    #     self._attr_available = True
    #     self._attr_native_value = 21
