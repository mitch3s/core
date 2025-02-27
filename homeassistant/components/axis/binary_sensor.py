"""Support for Axis binary sensors."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from axis.models.event import Event, EventGroup, EventOperation, EventTopic
from axis.vapix.interfaces.applications.fence_guard import FenceGuardHandler
from axis.vapix.interfaces.applications.loitering_guard import LoiteringGuardHandler
from axis.vapix.interfaces.applications.motion_guard import MotionGuardHandler
from axis.vapix.interfaces.applications.vmd4 import Vmd4Handler

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .entity import AxisEventEntity
from .hub import AxisHub

DEVICE_CLASS = {
    EventGroup.INPUT: BinarySensorDeviceClass.CONNECTIVITY,
    EventGroup.LIGHT: BinarySensorDeviceClass.LIGHT,
    EventGroup.MOTION: BinarySensorDeviceClass.MOTION,
    EventGroup.SOUND: BinarySensorDeviceClass.SOUND,
}

EVENT_TOPICS = (
    EventTopic.DAY_NIGHT_VISION,
    EventTopic.FENCE_GUARD,
    EventTopic.LOITERING_GUARD,
    EventTopic.MOTION_DETECTION,
    EventTopic.MOTION_DETECTION_3,
    EventTopic.MOTION_DETECTION_4,
    EventTopic.MOTION_GUARD,
    EventTopic.OBJECT_ANALYTICS,
    EventTopic.PIR,
    EventTopic.PORT_INPUT,
    EventTopic.PORT_SUPERVISED_INPUT,
    EventTopic.SOUND_TRIGGER_LEVEL,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a Axis binary sensor."""
    hub = AxisHub.get_hub(hass, config_entry)

    @callback
    def async_create_entity(event: Event) -> None:
        """Create Axis binary sensor entity."""
        async_add_entities([AxisBinarySensor(event, hub)])

    hub.api.event.subscribe(
        async_create_entity,
        topic_filter=EVENT_TOPICS,
        operation_filter=EventOperation.INITIALIZED,
    )


class AxisBinarySensor(AxisEventEntity, BinarySensorEntity):
    """Representation of a binary Axis event."""

    def __init__(self, event: Event, hub: AxisHub) -> None:
        """Initialize the Axis binary sensor."""
        super().__init__(event, hub)
        self.cancel_scheduled_update: Callable[[], None] | None = None

        self._attr_device_class = DEVICE_CLASS.get(event.group)
        self._attr_is_on = event.is_tripped

        self._set_name(event)

    @callback
    def async_event_callback(self, event: Event) -> None:
        """Update the sensor's state, if needed."""
        self._attr_is_on = event.is_tripped

        @callback
        def scheduled_update(now: datetime) -> None:
            """Timer callback for sensor update."""
            self.cancel_scheduled_update = None
            self.async_write_ha_state()

        if self.cancel_scheduled_update is not None:
            self.cancel_scheduled_update()
            self.cancel_scheduled_update = None

        if self.is_on or self.hub.option_trigger_time == 0:
            self.async_write_ha_state()
            return

        self.cancel_scheduled_update = async_call_later(
            self.hass,
            timedelta(seconds=self.hub.option_trigger_time),
            scheduled_update,
        )

    @callback
    def _set_name(self, event: Event) -> None:
        """Set binary sensor name."""
        if (
            event.group == EventGroup.INPUT
            and event.id in self.hub.api.vapix.ports
            and self.hub.api.vapix.ports[event.id].name
        ):
            self._attr_name = self.hub.api.vapix.ports[event.id].name

        elif event.group == EventGroup.MOTION:
            event_data: FenceGuardHandler | LoiteringGuardHandler | MotionGuardHandler | Vmd4Handler | None = None
            if event.topic_base == EventTopic.FENCE_GUARD:
                event_data = self.hub.api.vapix.fence_guard
            elif event.topic_base == EventTopic.LOITERING_GUARD:
                event_data = self.hub.api.vapix.loitering_guard
            elif event.topic_base == EventTopic.MOTION_GUARD:
                event_data = self.hub.api.vapix.motion_guard
            elif event.topic_base == EventTopic.MOTION_DETECTION_4:
                event_data = self.hub.api.vapix.vmd4
            if (
                event_data
                and event_data.initialized
                and (profiles := event_data["0"].profiles)
            ):
                for profile_id, profile in profiles.items():
                    camera_id = profile.camera
                    if event.id == f"Camera{camera_id}Profile{profile_id}":
                        self._attr_name = f"{self._event_type} {profile.name}"
                        return

            if (
                event.topic_base == EventTopic.OBJECT_ANALYTICS
                and self.hub.api.vapix.object_analytics.initialized
                and (scenarios := self.hub.api.vapix.object_analytics["0"].scenarios)
            ):
                for scenario_id, scenario in scenarios.items():
                    device_id = scenario.devices[0]["id"]
                    if event.id == f"Device{device_id}Scenario{scenario_id}":
                        self._attr_name = f"{self._event_type} {scenario.name}"
                        break
