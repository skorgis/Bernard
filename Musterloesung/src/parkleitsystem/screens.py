"""What the entry sign shows; one type per kind of screen."""

from dataclasses import dataclass

from parkleitsystem.domain import Side


@dataclass(frozen=True, slots=True)
class FreeSpaces:
    """Idle: no car is waiting, show how many spaces are free."""

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
