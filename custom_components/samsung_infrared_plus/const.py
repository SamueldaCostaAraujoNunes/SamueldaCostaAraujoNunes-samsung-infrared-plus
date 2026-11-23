"""Constants for the Samsung Infrared Plus integration."""

from enum import StrEnum

DOMAIN = "samsung_infrared_plus"
CONF_INFRARED_EMITTER_ENTITY_ID = "infrared_emitter_entity_id"
CONF_INFRARED_RECEIVER_ENTITY_ID = "infrared_receiver_entity_id"
CONF_DEVICE_TYPE = "device_type"

UNIQUE_ID_PREFIX = "samsung_infrared_plus_"


class SamsungDeviceType(StrEnum):
    """Samsung device types."""

    TV = "tv"
    AC = "ac"
