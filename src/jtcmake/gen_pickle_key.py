import secrets


def gen_key():
    return secrets.token_hex(32)


def _main():
    print(gen_key())


if __name__ == "__main__":
    _main()
