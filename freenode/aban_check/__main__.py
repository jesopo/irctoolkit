import argparse, asyncio
from . import main

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Find expired/deleted/etc accounts on freenode banlist")
    parser.add_argument("nickname")
    parser.add_argument("channel")
    parser.add_argument("outfile")
    parser.add_argument("--non-existent", "-n", action="store_true")
    args = parser.parse_args()

    print(args.non_existent)
    asyncio.run(main(
        args.nickname,
        args.channel,
        args.outfile,
        args.non_existent
    ))
