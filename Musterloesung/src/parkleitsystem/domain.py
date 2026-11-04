"""Parking spaces and their occupancy, independent of MQTT and hardware."""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class Side(StrEnum):
    """Where a parking space lies, seen from the entry sign."""

    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True, slots=True)
class ParkingSpace:
    """One parking space: a BMA region of interest with its own LED."""

    roi_name: str
    side: Side
    led_contact: int


class UnknownSpaceError(KeyError):
    """Raised for a region of interest that is not a configured space."""


class ParkingLot:
    """Occupancy of all configured parking spaces.

    A space whose state has not been reported yet counts as neither free nor
    occupied, so a freshly started program never sends cars to a space it
    knows nothing about.
    """

    def __init__(self, spaces: Iterable[ParkingSpace]) -> None:
        """Track `spaces`; their `roi_name`s must be unique."""
        self._spaces: dict[str, ParkingSpace] = {}
        for space in spaces:
            if space.roi_name in self._spaces:
                raise ValueError(f"duplicate parking space {space.roi_name!r}")
            self._spaces[space.roi_name] = space
        self._occupied: dict[str, bool] = {}

    def space(self, roi_name: str) -> ParkingSpace:
        """Return the configuration of the space named `roi_name`."""
        try:
            return self._spaces[roi_name]
        except KeyError as err:
            raise UnknownSpaceError(roi_name) from err

    def update(self, roi_name: str, *, occupied: bool) -> bool:
        """Record the state of a space; return whether it changed."""
        self.space(roi_name)
        changed = self._occupied.get(roi_name) != occupied
        self._occupied[roi_name] = occupied
        return changed

    @property
    def free_count(self) -> int:
        """Number of spaces reported vacant."""
        return sum(self._free_by_side().values())

    def best_side(self) -> Side | None:
        """Side with the most free spaces; left wins a tie, None if full."""
        free_by_side = self._free_by_side()
        # max() returns the first maximum, so the order of Side decides ties.
        best = max(Side, key=lambda side: free_by_side[side])
        return best if free_by_side[best] > 0 else None

    def _free_by_side(self) -> dict[Side, int]:
        free = dict.fromkeys(Side, 0)
        for name, occupied in self._occupied.items():
            if not occupied:
                free[self._spaces[name].side] += 1
        return free
