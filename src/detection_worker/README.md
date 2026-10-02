# detection_worker

Correlates Bernard detection events from two MQTT sources into "same vehicle"
pairs.

A typical setup has two devices along a road, for example a **BMA**
(hard-shoulder / emergency-lane camera) and a **BCA** (ANPR camera). Both
publish Bernard event-schema 6.0 messages over MQTT. When one vehicle passes
both devices, each one emits an event a few hundred milliseconds apart.
`detection_worker` subscribes to both topics, parses the messages, and pairs
events whose timestamps fall within a configurable tolerance. It reports
everything that cannot be paired as *unmatched*.

For the design (layers, message flow, correlation algorithm, threading
model), see [ARCHITECTURE.md](ARCHITECTURE.md).

## Package layout

| Module | Responsibility |
| --- | --- |
| `transport/client.py` | Thin wrapper around `paho-mqtt` (`Client`, `MqttConfig`, `MqttClient` protocol). No correlation logic. |
| `data/models/` | Dataclasses for the Bernard event schema 6.0 (`Event`, `CrossingLineEvent`, `OriginDestinationEvent`, …). |
| `data/parsing/parser.py` | `parse_event(...)`: JSON (str / bytes / dict, optionally zlib-compressed) → `Event`. |
| `correlation/event_timestamp.py` | `extract_timestamp(event)`: picks the timestamp that represents when an event happened. |
| `correlation/correlator.py` | `EventCorrelator`: transport-agnostic, timestamp-based pairing of two event streams. |
| `service/correlated_service.py` | `CorrelatedEventService`: one MQTT client, **one** topic pair. |
| `service/multi_site_service.py` | `MultiSiteCorrelatedService`: one MQTT client, **many** sites (topic pairs), each with its own correlator. Also handles jam lines and hot reload. |
| `config.py` | `load_config(path)` for the single-pair service; `MultiSiteServiceConfig` container. |

The layers only depend inwards: `service` → `correlation` / `data` /
`transport`. `correlation` and `data` know nothing about MQTT, so you can use
and test them offline.

## Setup

From the repository root:

```bash
uv sync
```

The only runtime dependency is `paho-mqtt`. Python ≥ 3.12 is required, because
the package uses PEP 695 generics.

## Usage

### 1. Single topic pair: `CorrelatedEventService`

Create a JSON config, e.g. `worker.json`:

```json
{
  "broker_host": "mqtt.example.com",
  "broker_port": 1883,
  "client_id": "detection-worker",
  "broker_username": null,
  "broker_password": null,
  "topic_a": "bma/events",
  "topic_b": "bca/events",
  "tolerance_seconds": 1.0,
  "leading_source": "a"
}
```

- `tolerance_seconds`: the maximum time between the two events of one vehicle.
- `leading_source`: `"a"` or `"b"`. It names the device the vehicle passes
  **first**. Defaults to `"a"`.

Then start the worker:

```bash
uv run detection-worker worker.json                     # INFO logging
uv run detection-worker worker.json --log-level DEBUG   # also logs paho's socket/TLS events
```

It runs until you press Ctrl+C or it receives SIGTERM (e.g. `docker stop`), and
disconnects cleanly in both cases. Pairs are logged at INFO and unmatched
events at WARNING.

To act on the pairs yourself instead of only logging them, build the service
in Python and pass your own callbacks:

```python
import logging
import signal

from detection_worker.config import load_config
from detection_worker.service.correlated_service import CorrelatedEventService
from detection_worker.transport.client import Client

logging.basicConfig(level=logging.INFO)

config = load_config("worker.json")
service = CorrelatedEventService(
    client=Client(config.mqtt),
    topic_a=config.topic_a,
    topic_b=config.topic_b,
    tolerance=config.tolerance,
    leading_source=config.leading_source,
    # Optional; by default pairs are logged at INFO, unmatched at WARNING.
    on_pair=lambda a, b: print("pair", a.timestamp, b.timestamp),
    on_unmatched=lambda m: print("unmatched", m.source, m.timestamp),
)

service.start()  # connects and starts paho's background loop
try:
    signal.pause()  # keep the main thread alive until Ctrl+C
except KeyboardInterrupt:
    pass
finally:
    service.stop()
```

`a.event` / `b.event` in the callbacks are fully parsed `Event` objects, e.g.
`a.event.crossingLineEvent.numberPlate`.

### 2. Many sites: `MultiSiteCorrelatedService`

Use this when one broker carries several BMA/BCA pairs. Every `Site` gets its
own correlator, so events from different sites are never paired with each
other. All sites share one MQTT connection, because the broker allows only one
live connection per client id.

A topic can carry events for several virtual lines. Only the line named in
the site config is correlated, and everything else on that topic is ignored.

```python
from datetime import timedelta

from detection_worker.service.multi_site_service import (
    MultiSiteCorrelatedService,
    Site,
)
from detection_worker.transport.client import Client, MqttConfig

sites = [
    Site(
        name="innsbruck-north",
        topic_bma="site1/bma/events",
        topic_bca="site1/bca/events",
        line_name_bma="hard-shoulder",  # crossingLineEvent.lineName
        line_name_bca="anpr",
        tolerance=timedelta(seconds=1.5),
        leading_role="bma",  # vehicles pass the BMA line first
        line_name_jam="jam-detection",  # optional third line on topic_bma
    ),
    Site(
        name="kufstein",
        topic_bma="site2/bma/events",
        topic_bca="site2/bca/events",
        line_name_bma="entry-zone",
        line_type_bma="origin_destination",  # match an O/D zone name instead
        line_name_bca="anpr",
        tolerance=timedelta(seconds=3),
        leading_role="bca",
        symmetric_tolerance=True,  # allow order jitter, see below
    ),
]

service = MultiSiteCorrelatedService(
    client=Client(
        MqttConfig("mqtt.example.com", 8883, "detection-worker", use_tls=True)
    ),
    sites=sites,
    on_pair=lambda site, a, b: print(site, "pair", a.timestamp, b.timestamp),
    on_unmatched=lambda site, m: print(site, "unmatched", m.source),
    on_jam=lambda site, ts, event: print(site, "jam-line event", ts),
    # Every event on a correlated line, before matching:
    on_event=lambda site, role, topic, ts, event: None,
)
service.start()
# ... later, e.g. after the site config changed:
service.reload(new_sites)
```

`Site` fields:

| Field | Meaning |
| --- | --- |
| `name` | Unique site id; passed as the first argument to every callback. |
| `topic_bma` / `topic_bca` | MQTT topics. A topic may belong to only one site. |
| `line_name_bma` / `line_name_bca` | Which line or zone on each topic gets correlated. |
| `line_type_bma` / `line_type_bca` | `"crossing_line"` (default) or `"origin_destination"` (matches the entry **or** exit zone name). |
| `tolerance` | This site's correlation window. |
| `leading_role` | `"bma"` or `"bca"`: which device the vehicle passes first. |
| `line_name_jam` / `line_type_jam` | Optional jam line on `topic_bma`. Its events go to `on_jam` and are never correlated. |
| `symmetric_tolerance` | Allow the trailing event up to `tolerance` *before* the leading one (default `False`). |

`reload(sites)` compares sites by value. Unchanged sites keep their correlator
and their pending events. A site that was added or changed is registered
again from scratch. A removed site is unsubscribed.

### 3. Typed event handlers: `EventDispatcher`

Besides correlation, you can register handlers for specific sub-events. Each
handler has a `HandlerKey(topic, name, event_type)` and is called with the
whole message and the sub-event, already typed as `event_type`:

```python
from detection_worker.data import (
    CrossingLineEvent,
    Event,
    HeatmapEvent,
    VirtualDoorEvent,
)
from detection_worker.dispatch import EventDispatcher, HandlerKey


def on_door(event: Event, door: VirtualDoorEvent) -> None:
    print(event.stream.name, door.virtualDoorName, door.direction)


def on_any_line(event: Event, line: CrossingLineEvent) -> None:
    print(line.lineName, line.numberPlate)


dispatcher = EventDispatcher()
dispatcher.add_handler(
    HandlerKey("site1/bma/events", "door-1", VirtualDoorEvent), on_door
)
dispatcher.add_handler(
    HandlerKey("site1/bma/events", None, CrossingLineEvent), on_any_line
)
dispatcher.add_handler(
    HandlerKey("site1/heatmap", None, HeatmapEvent),
    lambda event, heatmap: print(len(heatmap.path)),
)

# Pass it to either service; works the same for MultiSiteCorrelatedService.
service = CorrelatedEventService(..., dispatcher=dispatcher)
```

- **Event types:** `CrossingLineEvent`, `RegionOfInterestEvent`,
  `ParkingEvent`, `VirtualDoorEvent`, `OriginDestinationEvent` and
  `HeatmapEvent` (together, `detection_worker.dispatch.SubEvent`).
- **What `name` matches:** `lineName`, `roiName`, `virtualDoorName`, the
  entry *or* exit zone of an origin/destination event, or any `roiName` in a
  parking summary. `name=None` matches every event of that type on the topic.
  This is the only way to select heatmap events, which have no name.
- **Nested events:** sub-events inside `ruleEvents` are dispatched too.
- **Topics:** the services also subscribe to every topic in the dispatcher's
  keys, so a handler can listen on a topic no correlated pair or site uses.
  Register all handlers before `start()`, because topics added later are not
  subscribed.
- **Order and errors:** handlers run before correlation. A handler that raises
  is logged and skipped, and correlation still runs.
- **One handler per key:** registering a second handler for the same key
  raises `ValueError`.

You register handlers through `add_handler` rather than passing a plain dict,
because that keeps the typing checked. pyright rejects a handler whose second
parameter doesn't match the key's `event_type`, much like `std::visit` checks
its overload set in C++. Inside, the dispatcher still is a
`dict[HandlerKey, Handler]`.

### 4. Offline: correlator and parser alone

`EventCorrelator` is generic and does not need MQTT. This makes it handy for
notebooks, replaying recorded data, or tests:

```python
from datetime import datetime, timedelta
from detection_worker.correlation.correlator import EventCorrelator

correlator = EventCorrelator[str](
    tolerance=timedelta(seconds=1),
    leading_source="bma",
    on_pair=lambda a, b: print("pair:", a.event, "<->", b.event),
    on_unmatched=lambda m: print("unmatched:", m.source, m.event),
)
t0 = datetime(2026, 10, 1, 12, 0, 0)
correlator.add("bma", t0, "car-1")
# -> pair: car-1 <-> car-1
correlator.add("bca", t0 + timedelta(milliseconds=300), "car-1")
correlator.add("bma", t0 + timedelta(seconds=5), "car-2")
# -> unmatched: bma car-2
correlator.add("bca", t0 + timedelta(seconds=9), "car-3")
# car-3 stays pending until a later "bma" event moves time forward
```

Parsing a raw message (str, bytes, a decoded dict, or zlib-compressed bytes):

```python
from detection_worker.correlation.event_timestamp import extract_timestamp
from detection_worker.data import parse_event

event = parse_event(payload)
print(event.crossingLineEvent.lineName, extract_timestamp(event))
```

## How matching works

- **FIFO, not nearest neighbour.** The oldest pending event from the leading
  source is paired with the oldest pending event from the trailing source if
  `0 <= trailing - leading <= tolerance`. With `symmetric=True` the window is
  `-tolerance <= delay <= tolerance` instead.
- **Eviction is driven by event time.** A pending event is reported as
  unmatched once the *other* source's newest timestamp proves it can no longer
  match.
- **Buffers are bounded.** If one device goes silent, the other device's
  pending events are still reported as unmatched once they're more than
  `max_pending_age` (default 5 min) older than its own newest event.
  `max_pending` (default 10,000) caps each buffer. Pass either to
  `EventCorrelator`, or `None` to disable it.
- **`symmetric` is a trade-off.** It tolerates devices whose reported order
  jitters by a few milliseconds. It also makes it more likely that two
  different vehicles get paired when one device misses a reading. Enable it
  only per site, and only where that risk is acceptable.
- **Which timestamp is used.** `extract_timestamp` prefers the envelope's
  `timestamp`. Otherwise it uses the populated sub-event's own timestamp: the
  exit time for origin/destination events, the last path point for heatmap
  events, and the first resolvable entry for `ruleEvents`.

## Operational notes

- Subscriptions are made in the on-connect handler, so they survive the
  automatic reconnects done by paho.
- The reconnect backoff is set to 5–30 s on purpose. A broker that still holds
  a session for a fixed client id can otherwise reject fast reconnects in a
  tight loop.
- An exception raised while handling a message is logged and that message is
  skipped. It never kills paho's network thread.
- For hard-to-diagnose disconnects, call `client.enable_debug_logging()` and
  set the log level to `DEBUG`.

## Known gaps

- The `detection-worker` command only runs the single-pair service.
  `MultiSiteServiceConfig` has no file loader yet (in the original project it
  was built from Django settings), so for many sites you build the `Site` list
  in Python as shown above.
