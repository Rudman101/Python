"""Canonical serialization + hashing for determinism proofs.

Every hash captured by the replay engine (input-evidence hash, output hash,
policy/config hash) goes through canonical_json() first so that two runs
over identical logical input always produce byte-identical serialized text,
and therefore identical hashes, regardless of dict insertion order or
Python object identity.
"""
import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any


def _default(o: Any) -> Any:
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Enum):
        return o.value
    if is_dataclass(o) and not isinstance(o, type):
        return asdict(o)
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    raise TypeError(f"Object of type {type(o).__name__} is not canonically serializable")


def canonical_json(obj: Any) -> str:
    """Deterministic JSON text: sorted keys, fixed separators, ISO timestamps."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_default)


def sha256_hex(obj: Any) -> str:
    """SHA-256 hex digest of obj's canonical JSON representation."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()
