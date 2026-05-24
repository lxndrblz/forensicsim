"""
Snappy + Blink-V8 wrapper unwrap (fix per a issue #89).

A partir d'algun moment al 2025-2026, Microsoft Teams (i potencialment altres
apps Chromium) comencen a emmagatzemar valors grans d'IndexedDB amb un wrapper
de compressió Snappy. `ccl_chromium_reader.ccl_v8_value_deserializer` espera el
byte de header V8 (`0xFF` `kVersion`) com a primer byte i pèta amb
`ValueError("Didn't get version tag in the header")` quan veu el byte `0x02`
del wrapper Snappy.

Format detectat empíricament:

    byte 0:     0x02                      ← marker Snappy compression
    bytes 1+:   Snappy-compressed blob → after decompression:
                  ff 15                   ← V8 wrapper version 21 (Blink-V8 envelope)
                  fe 00 00 ... 00         ← kBlinkVersion token + padding
                  ff 0f                   ← V8 inner version 15
                  ...                     ← V8 standard data

`install_snappy_unwrap_patch()` monkey-patches
`ccl_v8_value_deserializer.Deserializer.__init__` per detectar i descomprimir
transparentment, deixant el deserializer veure únicament el V8 inner net.

Sense aquest patch, els builds de Teams 2026 perden ~95% de cobertura sobre
`replychains` (cos dels missatges) al perfil principal d'usuari.
"""
from __future__ import annotations

import io
import logging

import ccl_simplesnappy
from ccl_chromium_reader.serialization_formats import ccl_v8_value_deserializer as v8mod

log = logging.getLogger(__name__)

_SNAPPY_MARKER = 0x02
_V8_VERSION_TAG = 0xFF
_PATCH_INSTALLED = False
_ORIG_INIT = None


def _try_unwrap_snappy(data: bytes) -> bytes | None:
    """If `data` is Snappy-wrapped (byte 0 == 0x02), decompress and skip
    Blink-V8 envelope. Returns clean V8 payload, or None if not wrapped.
    """
    if not data or data[0] != _SNAPPY_MARKER:
        return None
    try:
        stream = io.BytesIO(data[1:])
        decompressed = ccl_simplesnappy.decompress(stream)
    except Exception as e:
        log.debug("snappy decompress failed: %s", e)
        return None

    if len(decompressed) < 4 or decompressed[0] != _V8_VERSION_TAG:
        return decompressed

    # Skip Blink-V8 outer envelope: find SECOND 0xFF (inner V8 version)
    second_ff = decompressed.find(bytes([_V8_VERSION_TAG]), 2)
    if second_ff == -1:
        return decompressed
    return decompressed[second_ff:]


def _patched_init(self, stream, host_object_delegate, *,
                  is_little_endian=True, is_64bit=True):
    """Replacement Deserializer.__init__ that auto-unwraps Snappy if present."""
    pos = stream.tell()
    try:
        first = stream.read(1)
        stream.seek(pos)
    except Exception:
        first = b""

    if first == bytes([_SNAPPY_MARKER]):
        try:
            full = stream.read()
            unwrapped = _try_unwrap_snappy(full)
            if unwrapped is not None:
                return _ORIG_INIT(
                    self, io.BytesIO(unwrapped), host_object_delegate,
                    is_little_endian=is_little_endian, is_64bit=is_64bit,
                )
        except Exception as e:
            log.debug("unwrap pipeline failed: %s — falling back to raw stream", e)
            stream.seek(pos)

    return _ORIG_INIT(
        self, stream, host_object_delegate,
        is_little_endian=is_little_endian, is_64bit=is_64bit,
    )


def install_snappy_unwrap_patch() -> None:
    """Install the monkey-patch globally. Idempotent — safe to call multiple times.

    Call this once at program startup, before any LevelDB iteration starts.
    """
    global _PATCH_INSTALLED, _ORIG_INIT
    if _PATCH_INSTALLED:
        return
    _ORIG_INIT = v8mod.Deserializer.__init__
    v8mod.Deserializer.__init__ = _patched_init
    _PATCH_INSTALLED = True
    log.info("Snappy unwrap patch installed (fix for issue #89)")
