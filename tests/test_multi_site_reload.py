"""Tests for thread-safe `MultiSiteCorrelatedService.reload`."""

import json
import threading
from datetime import timedelta

from detection_worker.service.multi_site_service import (
    MultiSiteCorrelatedService,
    Site,
)
from tests.fake_mqtt_client import FakeClient

WAIT_SECONDS = 2


def _site(name: str) -> Site:
    return Site(
        name=name,
        topic_bma=f"{name}/bma",
        topic_bca=f"{name}/bca",
        line_name_bma="hard-shoulder",
        line_name_bca="anpr",
        tolerance=timedelta(seconds=1),
        leading_role="bma",
    )


def _crossing_payload() -> bytes:
    return json.dumps(
        {
            "uuid": "e1",
            "version": "6.0",
            "eventSchema": "6.0",
            "node": {"id": "n1", "name": "cam"},
            "stream": {"id": "s1", "name": "lane"},
            "crossingLineEvent": {
                "class": "car",
                "lineId": "l1",
                "lineName": "hard-shoulder",
                "direction": "in",
                "timestamp": "2026-10-01T12:00:00+00:00",
            },
        }
    ).encode()


def test_reload_waits_for_message_in_progress() -> None:
    """`reload` from another thread can't interleave with a message."""
    client = FakeClient()
    handling = threading.Event()
    release = threading.Event()

    def blocking_on_event(*_args: object) -> None:
        handling.set()
        release.wait(WAIT_SECONDS)

    service = MultiSiteCorrelatedService(
        client, [_site("s1")], on_event=blocking_on_event
    )
    assert client.on_message is not None
    on_message = client.on_message
    network_thread = threading.Thread(
        target=lambda: on_message("s1/bma", _crossing_payload())
    )
    network_thread.start()
    assert handling.wait(WAIT_SECONDS)

    reloaded = threading.Event()
    reload_thread = threading.Thread(
        target=lambda: (service.reload([]), reloaded.set())
    )
    reload_thread.start()

    try:
        assert not reloaded.wait(0.2), "reload ran while a message was mid-way"
    finally:
        release.set()
        network_thread.join(WAIT_SECONDS)
        reload_thread.join(WAIT_SECONDS)
    assert reloaded.is_set()


def test_reload_from_inside_a_callback_does_not_deadlock() -> None:
    """Callbacks run under the lock, so it must be re-entrant."""
    client = FakeClient()
    services: list[MultiSiteCorrelatedService] = []
    done = threading.Event()

    def reload_on_event(*_args: object) -> None:
        services[0].reload([_site("s1"), _site("s2")])
        done.set()

    services.append(
        MultiSiteCorrelatedService(
            client, [_site("s1")], on_event=reload_on_event
        )
    )
    assert client.on_message is not None
    on_message = client.on_message
    worker = threading.Thread(
        target=lambda: on_message("s1/bma", _crossing_payload()), daemon=True
    )
    worker.start()

    assert done.wait(WAIT_SECONDS), "reload inside a callback deadlocked"
