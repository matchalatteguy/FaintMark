"""Shortened BCH(127,71,t=8) over GF(2^7), primitive poly x^7+x^3+1: 40 data + 56 parity bits (TrustMark BCH_SUPER)."""

M, POLY, T, PARITY, DATA = 7, 0b10001001, 8, 56, 40
N = DATA + PARITY
EXP, LOG = [0] * 254, [0] * 128
_x = 1
for _i in range(127):
    EXP[_i] = EXP[_i + 127] = _x
    LOG[_x] = _i
    _x <<= 1
    if _x & 128:
        _x ^= POLY


def _mul(a, b):
    return EXP[LOG[a] + LOG[b]] if a and b else 0


def _generator():
    roots = {i * 2**j % 127 for i in range(1, 2 * T, 2) for j in range(M)}
    g = [1]
    for r in roots:
        g = [
            (g[j - 1] if j else 0) ^ (_mul(g[j], EXP[r]) if j < len(g) else 0)
            for j in range(len(g) + 1)
        ]
    return sum(1 << j for j, c in enumerate(g) if c)


G = _generator()


def encode(data):
    """40-bit int -> 96-bit codeword int: data bits (MSB first) then parity bits."""
    v = data << PARITY
    for s in range(v.bit_length() - 1, PARITY - 1, -1):
        if v >> s & 1:
            v ^= G << (s - PARITY)
    return data << PARITY | v


def decode(word):
    """96-bit codeword int -> (data, ok). If uncorrectable, data is the uncorrected data bits and ok is False."""
    syn = [0] + [0] * (2 * T)
    for d in range(N):
        if word >> d & 1:
            for j in range(1, 2 * T + 1):
                syn[j] ^= EXP[j * d % 127]
    if not any(syn):
        return word >> PARITY, True
    # Berlekamp-Massey: lam is the error locator, prev its last copy before a length change,
    # L its degree, m the steps since that change and b the discrepancy at that change
    lam, prev, L, m, b = [1] + [0] * (2 * T), [1] + [0] * (2 * T), 0, 1, 1
    for n in range(2 * T):
        d = syn[n + 1]
        for i in range(1, L + 1):
            d ^= _mul(lam[i], syn[n + 1 - i])
        if d == 0:
            m += 1
            continue
        old, c = lam[:], EXP[(LOG[d] - LOG[b]) % 127]
        for i in range(2 * T + 1 - m):
            lam[i + m] ^= _mul(c, prev[i])
        if 2 * L <= n:
            L, prev, b, m = n + 1 - L, old, d, 1
        else:
            m += 1
    errors = [d for d in range(N) if not _eval(lam, L, d)]
    if L > T or len(errors) != L:
        return word >> PARITY, False
    for d in errors:
        word ^= 1 << d
    return word >> PARITY, True


def _eval(lam, L, d):
    s = 0
    for i in range(L + 1):
        s ^= _mul(lam[i], EXP[-d * i % 127])
    return s
