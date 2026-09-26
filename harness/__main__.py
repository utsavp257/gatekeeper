import sys

from harness.config import ConfigError, load_settings
from harness.db import ping


def main(argv: list[str]) -> int:
    if argv[:1] != ["ping"]:
        print("usage: python -m harness ping")
        return 2
    try:
        settings = load_settings()
        ping(settings)
    except ConfigError as e:
        print(f"✗ {e}")
        return 1
    print(f"✓ Atlas reachable, database = {settings.mongodb_db}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
