import argparse, asyncio
from . import main

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Bot for freenode to detect JOIN preventers")

    parser.add_argument("nickname")
    parser.add_argument("--sasl",
        help="SASL username and password (e.g. jess:hunter2)")
    args = parser.parse_args()

    asyncio.run(main(args.nickname, args.sasl))
