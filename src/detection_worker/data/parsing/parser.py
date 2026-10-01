"""JSON parsing of the Bernard event schema (v6.0) into dataclasses."""

import dataclasses
import json
import types
import typing
import zlib
from typing import Any

from detection_worker.data.models.event import Event

_JSON_KEY_OVERRIDES = {"class_": "class"}
# zlib (RFC 1950) header: CMF=0x78, FLG varies with compression level/
# strategy (e.g. 0x9c default, 0xda best compression) — the low nibble of
# CMF encodes the compression method (8 = deflate), the only one zlib uses.
_ZLIB_MAGIC = b"\x78"


def parse_event(data: str | bytes | dict[str, Any]) -> Event:
    """Parse a JSON event message (string, bytes, or decoded dict).

    Bytes payloads prefixed with the zlib header are transparently
    decompressed before parsing.
    """
    if isinstance(data, bytes):
        data = _maybe_unzlib(data)
    decoded: dict[str, Any] = (
        json.loads(data) if isinstance(data, str | bytes) else data
    )
    return from_dict(Event, decoded)


def _maybe_unzlib(data: bytes) -> bytes:
    if data.startswith(_ZLIB_MAGIC):
        return zlib.decompress(data)
    return data


def from_dict[T](cls: type[T], data: dict[str, Any]) -> T:
    """Build a dataclass instance of `cls` from a decoded JSON object."""
    return _parse(cls, data)


def _parse(annotation: Any, value: Any) -> Any:
    annotation = _resolve_alias(annotation)

    if value is None:
        return None

    if dataclasses.is_dataclass(annotation):
        dataclass_type = typing.cast("type[Any]", annotation)
        hints = typing.get_type_hints(dataclass_type)
        kwargs = {}
        for field in dataclasses.fields(dataclass_type):
            json_key = _JSON_KEY_OVERRIDES.get(field.name, field.name)
            if json_key in value:
                kwargs[field.name] = _parse(hints[field.name], value[json_key])
        return dataclass_type(**kwargs)

    origin = typing.get_origin(annotation)
    if origin is types.UnionType or origin is typing.Union:
        (inner,) = (
            a for a in typing.get_args(annotation) if a is not type(None)
        )
        return _parse(inner, value)
    if origin is list:
        (item_type,) = typing.get_args(annotation)
        return [_parse(item_type, item) for item in value]
    if origin is dict:
        return dict(value)

    return value


def _resolve_alias(annotation: Any) -> Any:
    while isinstance(annotation, typing.TypeAliasType):
        annotation = annotation.__value__
    return annotation
