import random

from faintmark.bch import N, decode, encode

IDS = [0, 1, 2**40 - 1, 0xDEADBEEF42, 0x0123456789, 1 << 39]


def flip(word, count, rng):
    for bit in rng.sample(range(N), count):
        word ^= 1 << bit
    return word


def test_roundtrip():
    rng = random.Random(1)
    for data in IDS + [rng.getrandbits(40) for _ in range(300)]:
        assert decode(encode(data)) == (data, True)


def test_corrects_eight_flipped_bits():
    rng = random.Random(2)
    for data in IDS:
        for _ in range(20):
            assert decode(flip(encode(data), 8, rng)) == (data, True)


def test_nine_flipped_bits_are_rejected():
    rng = random.Random(3)
    for data in IDS:
        for _ in range(20):
            assert decode(flip(encode(data), 9, rng))[1] is False
