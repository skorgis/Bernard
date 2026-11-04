"""Use case: react to BMA observations with LEDs and the entry sign."""

import threading
from typing import Protocol

from parkleitsystem.domain import ParkingLot
from parkleitsystem.screens import FreeSpaces, Guidance, NoSpace, Screen


class LedSwitch(Protocol):
    """Switches one BMC contact (LED) permanently on or off."""

    def switch(self, contact: int, on: bool) -> None:
        """Set LED `contact` to `on`."""
        ...


class ParkingGuide:
    """Keeps LEDs and sign in line with the BMA's observations.

    MQTT callbacks (paho's network thread) feed observations in, while the
    main thread asks for the current screen, hence the lock. Times are
    monotonic seconds supplied by the caller, so tests need no real clock.
    """

    def __init__(
        self, lot: ParkingLot, leds: LedSwitch, *, guidance_s: float
    ) -> None:
        """Guide with `lot`; show an arrow for `guidance_s` per car."""
        self._lot = lot
        self._leds = leds
        self._guidance_s = guidance_s
        self._guidance_until = float("-inf")
        self._lock = threading.Lock()

    def on_space_state(self, roi_name: str, *, occupied: bool) -> None:
        """A parking space reported its state; switch its LED on change.

        Zones report every few seconds even without a change; sending a
        command only on change keeps the team well below bmc-interface's
        spam limit.
        """
        with self._lock:
            changed = self._lot.update(roi_name, occupied=occupied)
            contact = self._lot.space(roi_name).led_contact
        if changed:
            self._leds.switch(contact, occupied)

    def on_vehicle_entered(self, *, now: float) -> None:
        """A car crossed the entry line: show it the way."""
        with self._lock:
            self._guidance_until = now + self._guidance_s

    def screen(self, *, now: float) -> Screen:
        """What the sign should show at `now`."""
        with self._lock:
            free = self._lot.free_count
            side = self._lot.best_side()
            guiding = now < self._guidance_until
        if side is None:
            return NoSpace()
        if guiding:
            return Guidance(side=side, free=free)
        return FreeSpaces(free=free)
