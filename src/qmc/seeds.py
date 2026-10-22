"""Seeds: the job's master seed and one derived seed per shard.

Terms
- *Master seed*: 256 bits (32 bytes) taken from the job's Qrypt entropy block. Stored with the job.
- *Shard seed*: 256 bits calculated from the master seed and the shard's position. Never from the clock,
  never from a shared generator, so the same master seed always gives the same shard seeds.
- *HKDF* (HMAC-based Key Derivation Function, RFC 5869): a standard way to turn one secret value into many
  independent-looking values. "Extract" mixes the input into a fixed-size key; "expand" stretches that key
  into output bytes labelled by an ``info`` string. Here the label is the shard index and shard count.
"""

from __future__ import annotations

import hashlib
import hmac

from qmc import ALGO_VERSION

SEED_BYTES = 32
_HASH = hashlib.sha256
_HASH_LEN = 32


def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    """RFC 5869 section 2.2. An empty salt means a string of zero bytes of hash length."""
    if not salt:
        salt = b"\x00" * _HASH_LEN
    return hmac.new(salt, ikm, _HASH).digest()


def hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    """RFC 5869 section 2.3."""
    if length <= 0 or length > 255 * _HASH_LEN:
        raise ValueError("HKDF output length must be between 1 and 8160 bytes")
    out = b""
    block = b""
    counter = 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([counter]), _HASH).digest()
        out += block
        counter += 1
    return out[:length]


def hkdf(ikm: bytes, salt: bytes, info: bytes, length: int) -> bytes:
    """Extract then expand."""
    return hkdf_expand(hkdf_extract(salt, ikm), info, length)


def master_seed_from_block(block: bytes) -> bytes:
    """The master seed is the first 32 bytes of the Qrypt block (kept as-is so auditors can see them)."""
    if len(block) < SEED_BYTES:
        raise ValueError(f"entropy block too short: need at least {SEED_BYTES} bytes, got {len(block)}")
    return bytes(block[:SEED_BYTES])


def block_fingerprint(block: bytes) -> str:
    """SHA-256 of the whole entropy block, stored so the seed's origin can be checked later."""
    return hashlib.sha256(block).hexdigest()


def shard_seed(master_seed: bytes, shard_index: int, shard_count: int, version: str = ALGO_VERSION) -> bytes:
    """Derive the 32-byte seed for one shard.

    salt = the algorithm version label; info = "shard" + index + count as 4-byte big-endian numbers.
    The job id is deliberately not included, so a replay (a new job with the same master seed) gets the
    same shard seeds.
    """
    if len(master_seed) != SEED_BYTES:
        raise ValueError(f"master seed must be {SEED_BYTES} bytes")
    if shard_count < 1 or not 0 <= shard_index < shard_count:
        raise ValueError("shard_index must be in [0, shard_count)")
    info = b"shard" + shard_index.to_bytes(4, "big") + shard_count.to_bytes(4, "big")
    return hkdf(master_seed, version.encode(), info, SEED_BYTES)


def shard_seeds(master_seed: bytes, shard_count: int, version: str = ALGO_VERSION) -> list[bytes]:
    return [shard_seed(master_seed, i, shard_count, version) for i in range(shard_count)]
