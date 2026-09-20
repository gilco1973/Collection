"""A small RSA key generator for the JWT tests (never used in production): Miller-Rabin primes, 1024-bit modulus."""
import random

def _is_probable_prime(n, k=16):
    if n < 4: return n in (2, 3)
    if n % 2 == 0: return False
    d, r = n - 1, 0
    while d % 2 == 0: d //= 2; r += 1
    for _ in range(k):
        a = random.randrange(2, n - 2); x = pow(a, d, n)
        if x in (1, n - 1): continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1: break
        else: return False
    return True

def _prime(bits, rnd):
    while True:
        c = rnd.getrandbits(bits) | (1 << (bits - 1)) | 1
        if _is_probable_prime(c): return c

def keypair(bits=1024, seed=7):
    rnd = random.Random(seed); random.seed(seed)
    e = 65537
    while True:
        p, q = _prime(bits // 2, rnd), _prime(bits // 2, rnd)
        n = p * q; phi = (p - 1) * (q - 1)
        if p != q and phi % e: break
    d = pow(e, -1, phi)
    return n, e, d
