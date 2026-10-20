"""Storm Relay M0 content package.

The public construction entry point is :func:`build_storm_relay_session`.
It returns a real Gameplay v0.4 ``GameplaySession`` backed by PMW Laws; later
M0 session/UI adapters deliberately build on this factory instead of owning a
second game-state model.
"""

from .content import build_storm_relay_session, make_storm_relay_world

__all__ = ("build_storm_relay_session", "make_storm_relay_world")
