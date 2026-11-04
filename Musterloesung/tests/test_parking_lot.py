import pytest

from parkleitsystem.domain import (
    ParkingLot,
    ParkingSpace,
    Side,
    UnknownSpaceError,
)

LEFT_1 = ParkingSpace("P1", Side.LEFT, led_contact=1)
LEFT_2 = ParkingSpace("P2", Side.LEFT, led_contact=2)
RIGHT_1 = ParkingSpace("P3", Side.RIGHT, led_contact=3)


def make_lot() -> ParkingLot:
    return ParkingLot([LEFT_1, LEFT_2, RIGHT_1])


def test_spaces_with_unknown_state_are_not_free() -> None:
    lot = make_lot()

    assert lot.free_count == 0
    assert lot.best_side() is None


def test_update_reports_only_real_changes() -> None:
    lot = make_lot()

    assert lot.update("P1", occupied=False) is True
    assert lot.update("P1", occupied=False) is False
    assert lot.update("P1", occupied=True) is True


def test_free_count_counts_vacant_spaces() -> None:
    lot = make_lot()
    lot.update("P1", occupied=False)
    lot.update("P2", occupied=True)
    lot.update("P3", occupied=False)

    assert lot.free_count == 2


def test_best_side_is_side_with_most_free_spaces() -> None:
    lot = make_lot()
    lot.update("P1", occupied=True)
    lot.update("P2", occupied=True)
    lot.update("P3", occupied=False)

    assert lot.best_side() is Side.RIGHT


def test_best_side_prefers_left_on_a_tie() -> None:
    lot = make_lot()
    lot.update("P1", occupied=False)
    lot.update("P2", occupied=True)
    lot.update("P3", occupied=False)

    assert lot.best_side() is Side.LEFT


def test_best_side_is_none_when_everything_is_occupied() -> None:
    lot = make_lot()
    for name in ("P1", "P2", "P3"):
        lot.update(name, occupied=True)

    assert lot.best_side() is None


def test_recommend_is_first_free_space_on_best_side() -> None:
    lot = make_lot()
    lot.update("P1", occupied=True)
    lot.update("P2", occupied=False)
    lot.update("P3", occupied=False)

    assert lot.recommend() == LEFT_2


def test_recommend_follows_configured_order() -> None:
    lot = make_lot()
    lot.update("P2", occupied=False)
    lot.update("P1", occupied=False)

    assert lot.recommend() == LEFT_1


def test_recommend_is_none_without_free_space() -> None:
    lot = make_lot()
    lot.update("P1", occupied=True)

    assert lot.recommend() is None


def test_update_of_unknown_space_raises() -> None:
    with pytest.raises(UnknownSpaceError):
        make_lot().update("P99", occupied=True)


def test_duplicate_space_names_are_rejected() -> None:
    with pytest.raises(ValueError, match="P1"):
        ParkingLot([LEFT_1, ParkingSpace("P1", Side.RIGHT, led_contact=9)])


def test_space_looks_up_configuration_by_name() -> None:
    assert make_lot().space("P3") == RIGHT_1
