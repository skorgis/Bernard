"""The car park: occupancy, LEDs, recommendation and the sign's screen.

No MQTT and no hardware in here, so everything can be tested on its own.
"""

import threading
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

# The recommended space's LED toggles every 0.5 s. One command per toggle:
# 10 s of guidance cost 20 commands per car, far below bmc-interface's spam
# limit of 600 commands per 5 minutes.
BLINK_HALF_PERIOD_S = 0.5


class Side(StrEnum):
    """Where a space lies, seen from a car crossing the entry line."""

    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True, slots=True)
class Space:
    """One parking space: BMA zone name, side and the BMC contact of its LED."""

    name: str
    side: Side
    led: int


# The three screens of the entry sign.


@dataclass(frozen=True, slots=True)
class FreeSpaces:
    """No car is entering: show how many spaces are free."""

    free: int


@dataclass(frozen=True, slots=True)
class Guidance:
    """A car is entering: arrow towards `side`, plus the free count."""

    side: Side
    free: int


@dataclass(frozen=True, slots=True)
class NoSpace:
    """No free space is known: show a cross."""


type Screen = FreeSpaces | Guidance | NoSpace


class Leds(Protocol):
    """Switches the LED on one BMC contact on or off."""

    def switch(self, led: int, on: bool) -> None:
        """Set LED `led` to `on`."""
        ...


class CarPark:
    """Keeps the LEDs and the sign in line with what the BMA reports.

    - An occupied space's LED is on, a free space's LED is off.
    - When a car enters, the LED of the recommended space blinks until the
      car parks there or `guidance_s` is over.
    - A space that has never reported counts as neither free nor occupied,
      so no car is sent to a space nothing is known about.

    MQTT messages arrive in paho's network thread while the main loop calls
    `tick` and `screen`, hence the lock. Times are seconds from
    `time.monotonic()`, passed in so tests need no real clock.
    """

    def __init__(self, spaces: list[Space], leds: Leds, *, guidance_s: float):
        """Track `spaces` (in order of preference) and switch `leds`."""
        self._spaces = {space.name: space for space in spaces}
        self._occupied: dict[str, bool] = {}
        self._leds = leds
        self._guidance_s = guidance_s
        self._guiding_until = float("-inf")
        self._blinking: Space | None = None
        self._blink_started = 0.0
        self._blink_led_on: bool | None = None  # None: nothing sent yet
        self._lock = threading.Lock()

    def space_reported(self, name: str, *, occupied: bool) -> None:
        """A zone reported its state; switch its LED if the state changed.

        Zones report every few seconds even without a change. Sending only
        changes keeps us far below bmc-interface's spam limit.
        """
        with self._lock:
            space = self._spaces.get(name)
            if space is None:
                return  # a zone that is not one of our spaces
            changed = self._occupied.get(name) != occupied
            self._occupied[name] = occupied
            if occupied and self._blinking == space:
                self._blinking = None  # the car has parked there
        if changed:
            self._leds.switch(space.led, occupied)

    def car_entered(self, *, now: float) -> None:
        """A car crossed the entry line: recommend it a space."""
        with self._lock:
            self._guiding_until = now + self._guidance_s
            commands = self._stop_blinking()
            self._blinking = self._recommend()
            self._blink_started = now
            self._blink_led_on = None
        self._send(commands)

    def tick(self, *, now: float) -> None:
        """Let the recommended LED blink; call this several times a second."""
        with self._lock:
            commands = self._blink(now)
        self._send(commands)

    def screen(self, *, now: float) -> Screen:
        """What the entry sign should show at `now`."""
        with self._lock:
            free = self._free_count()
            side = self._best_side()
            guiding = now < self._guiding_until
        if side is None:
            return NoSpace()
        if guiding:
            return Guidance(side=side, free=free)
        return FreeSpaces(free=free)

    # --- helpers, always called with the lock held -------------------------

    def _is_free(self, space: Space) -> bool:
        return self._occupied.get(space.name) is False

    def _free_count(self) -> int:
        return sum(self._is_free(space) for space in self._spaces.values())

    def _best_side(self) -> Side | None:
        """Side with the most free spaces; left wins a tie; None if full."""
        free = {side: 0 for side in Side}
        for space in self._spaces.values():
            if self._is_free(space):
                free[space.side] += 1
        best = Side.LEFT if free[Side.LEFT] >= free[Side.RIGHT] else Side.RIGHT
        return best if free[best] > 0 else None

    def _recommend(self) -> Space | None:
        """First free space on the best side, in configured order."""
        side = self._best_side()
        for space in self._spaces.values():
            if space.side is side and self._is_free(space):
                return space
        return None

    def _blink(self, now: float) -> list[tuple[int, bool]]:
        space = self._blinking
        if space is None:
            return []
        if now >= self._guiding_until:
            return self._stop_blinking()
        half_periods = int((now - self._blink_started) // BLINK_HALF_PERIOD_S)
        on = half_periods % 2 == 0
        if on == self._blink_led_on:
            return []
        self._blink_led_on = on
        return [(space.led, on)]

    def _stop_blinking(self) -> list[tuple[int, bool]]:
        """End blinking; return the command that restores the real state."""
        space, self._blinking = self._blinking, None
        if space is None or self._blink_led_on is None:
            return []
        occupied = not self._is_free(space)
        if self._blink_led_on == occupied:
            return []
        return [(space.led, occupied)]

    def _send(self, commands: list[tuple[int, bool]]) -> None:
        for led, on in commands:
            self._leds.switch(led, on)
