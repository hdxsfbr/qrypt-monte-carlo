import hashlib

import pytest

from qmc import seeds

# RFC 5869 Appendix A, test cases 1-3 (SHA-256).
RFC5869 = [
    (
        "0b" * 22,
        "000102030405060708090a0b0c",
        "f0f1f2f3f4f5f6f7f8f9",
        42,
        "077709362c2e32df0ddc3f0dc47bba6390b6c73bb50f9c3122ec844ad7c2b3e5",
        "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865",
    ),
    (
        bytes(range(0x00, 0x50)).hex(),
        bytes(range(0x60, 0xB0)).hex(),
        bytes(range(0xB0, 0x100)).hex(),
        82,
        "06a6b88c5853361a06104c9ceb35b45cef760014904671014a193f40c15fc244",
        "b11e398dc80327a1c8e7f78c596a49344f012eda2d4efad8a050cc4c19afa97c59045a99cac7827271cb41c65e590e09"
        "da3275600c2f09b8367793a9aca3db71cc30c58179ec3e87c14c01d5c1f3434f1d87",
    ),
    (
        "0b" * 22,
        "",
        "",
        42,
        "19ef24a32c717b167f33a91d6f648bdf96596776afdb6377ac434c1c293ccb04",
        "8da4e775a563c18f715f802a063c5a31b8a11f5c5ee1879ec3454e5f3c738d2d9d201395faa4b61a96c8",
    ),
]


@pytest.mark.parametrize(("ikm", "salt", "info", "length", "prk", "okm"), RFC5869)
def test_hkdf_matches_rfc5869(ikm, salt, info, length, prk, okm):
    assert seeds.hkdf_extract(bytes.fromhex(salt), bytes.fromhex(ikm)).hex() == prk
    assert seeds.hkdf_expand(bytes.fromhex(prk), bytes.fromhex(info), length).hex() == okm
    assert seeds.hkdf(bytes.fromhex(ikm), bytes.fromhex(salt), bytes.fromhex(info), length).hex() == okm


def test_hkdf_expand_rejects_bad_length():
    with pytest.raises(ValueError):
        seeds.hkdf_expand(b"k" * 32, b"", 0)
    with pytest.raises(ValueError):
        seeds.hkdf_expand(b"k" * 32, b"", 255 * 32 + 1)


MASTER = bytes(range(32))


def test_shard_seeds_are_deterministic():
    assert seeds.shard_seeds(MASTER, 50) == seeds.shard_seeds(MASTER, 50)


def test_shard_seeds_are_distinct():
    derived = seeds.shard_seeds(MASTER, 1000)
    assert len(set(derived)) == 1000
    assert all(len(s) == 32 for s in derived)
    assert MASTER not in derived


def test_shard_seed_depends_on_master_index_count_and_version():
    base = seeds.shard_seed(MASTER, 3, 10)
    other_master = bytes([1]) + MASTER[1:]
    assert seeds.shard_seed(other_master, 3, 10) != base
    assert seeds.shard_seed(MASTER, 4, 10) != base
    assert seeds.shard_seed(MASTER, 3, 11) != base
    assert seeds.shard_seed(MASTER, 3, 10, version="qmc-v2") != base


def test_shard_seed_is_pinned():
    # Regression pin: if this changes, ALGO_VERSION must change too (old jobs would no longer replay).
    assert (
        seeds.shard_seed(MASTER, 0, 1).hex()
        == seeds.hkdf(MASTER, b"qmc-v1", b"shard" + (0).to_bytes(4, "big") + (1).to_bytes(4, "big"), 32).hex()
    )


@pytest.mark.parametrize(("index", "count"), [(-1, 4), (4, 4), (0, 0)])
def test_shard_seed_rejects_bad_index(index, count):
    with pytest.raises(ValueError):
        seeds.shard_seed(MASTER, index, count)


def test_shard_seed_rejects_wrong_master_length():
    with pytest.raises(ValueError):
        seeds.shard_seed(b"short", 0, 1)


def test_master_seed_is_first_32_bytes_and_fingerprint_covers_block():
    block = bytes(range(256)) * 4
    assert seeds.master_seed_from_block(block) == block[:32]
    assert seeds.block_fingerprint(block) == hashlib.sha256(block).hexdigest()
    with pytest.raises(ValueError):
        seeds.master_seed_from_block(b"x" * 31)
