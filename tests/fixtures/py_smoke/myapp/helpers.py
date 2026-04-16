def hash_password(password):
    return _inner(password)


def _inner(p):
    return p.encode()
