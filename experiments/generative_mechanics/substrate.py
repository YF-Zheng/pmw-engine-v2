"""Frozen public substrate shared by all lab environments."""

CHANNELS = (
    "temperature",
    "wetness",
    "electric_field",
    "fire_intensity",
    "sound_level",
    "ground_stability",
    "water_level",
    "visibility",
)

CHANNEL_SET = frozenset(CHANNELS)
FIELD_MIN = 0.0
FIELD_MAX = 1.0

