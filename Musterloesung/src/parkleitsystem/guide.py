"""Use case: react to BMA observations with LEDs and the entry sign."""

import threading
from dataclasses import dataclass
from typing import Protocol

from parkleitsystem.domain import ParkingLot, ParkingSpace
from parkleitsystem.screens import FreeSpaces, Guidance, NoSpace, Screen

# Half a blink period in seconds (LED 0.5 s on, 0.5 s off). Each half period
# costs one command, so 10 s of guidance send 20 commands per car, well
# below bmc-interface's spam limit of 600 commands per 5 minutes.
BLINK_HALF_PERIOD_S = 0.5

type LedCommand = tuple[int, bool]


class LedSwitch(Protocol):
    """Switches one BMC contact (LED) permanently on or off."""

    def switch(self, contact: int, on: bool) -> None:
        """Set LED `contact` to `on`."""
        ...


@dataclass(slots=True)
class _Blink:
    """The recommended space whose LED blinks while a car is guided."""

    space: ParkingSpace
    started: float
    led_on: bool | None = None  # last state sent; None = nothing sent yet


class ParkingGuide:
    """Keeps LEDs and sign in line with the BMA's observations.

    An occupied space's LED is on, or a free space's with
    `lit_when_free` (green LEDs). When a car enters, the LED of the
    recommended free space blinks until the car parks there or the
    guidance time is over; `tick` must be called regularly to drive it.

    MQTT callbacks (paho's network thread) feed observations in, while the
    main thread ticks and asks for the current screen, hence the lock.
    Times are monotonic seconds supplied by the caller, so tests need no
    real clock.
    """

    def __init__(
        self,
        lot: ParkingLot,
        leds: LedSwitch,
        *,
        guidance_s: float,
        lit_when_free: bool = False,
    ) -> None:
        """Guide with `lot`; guide each car for `guidance_s`.

        `lit_when_free` lights a space's LED while it is free instead of
        while it is occupied.
        """
        self._lot = lot
        self._leds = leds
        self._guidance_s = guidance_s
        self._lit_when_free = lit_when_free
        self._guidance_until = float("-inf")
        self._blink: _Blink | None = None
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
            if occupied and self._is_blinking(roi_name):
                self._blink = None
        if changed:
            self._leds.switch(contact, self._lit(occupied=occupied))

    def on_vehicle_entered(self, *, now: float) -> None:
        """A car crossed the entry line: recommend it a space."""
        with self._lock:
            self._guidance_until = now + self._guidance_s
            commands = self._stop_blinking()
            space = self._lot.recommend()
            if space is not None:
                self._blink = _Blink(space, started=now)
        self._send(commands)

    def tick(self, *, now: float) -> None:
        """Advance the blinking LED to `now`."""
        with self._lock:
            commands = self._advance_blink(now)
        self._send(commands)

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

    def _is_blinking(self, roi_name: str) -> bool:
        return (
            self._blink is not None and self._blink.space.roi_name == roi_name
        )

    def _advance_blink(self, now: float) -> list[LedCommand]:
        blink = self._blink
        if blink is None:
            return []
        if now >= self._guidance_until:
            return self._stop_blinking()
        phase = int((now - blink.started) // BLINK_HALF_PERIOD_S)
        # The first phase inverts the free space's steady LED state, so the
        # blinking is visible at once.
        steady = self._lit(occupied=False)
        on = (phase % 2 == 0) != steady
        if on == blink.led_on:
            return []
        blink.led_on = on
        return [(blink.space.led_contact, on)]

    def _stop_blinking(self) -> list[LedCommand]:
        """End blinking; return the command restoring the real LED state."""
        blink, self._blink = self._blink, None
        if blink is None or blink.led_on is None:
            return []
        occupied = not self._lot.is_free(blink.space.roi_name)
        lit = self._lit(occupied=occupied)
        if blink.led_on == lit:
            return []
        return [(blink.space.led_contact, lit)]

    def _lit(self, *, occupied: bool) -> bool:
        """LED state that shows `occupied`."""
        return occupied != self._lit_when_free

    def _send(self, commands: list[LedCommand]) -> None:
        for contact, on in commands:
            self._leds.switch(contact, on)
