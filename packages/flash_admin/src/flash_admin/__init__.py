from flash_db import hello as db_hello


def hello() -> str:
    print(db_hello())
    return "Hello from flash-admin!"


if __name__ == "__main__":
    print(hello())
