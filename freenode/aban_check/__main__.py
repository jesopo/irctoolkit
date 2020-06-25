import argparse, asyncio
from . import main

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Find expired/deleted/etc accounts on freenode banlist")
    parser.add_argument("nickname")
    parser.add_argument("channel")
    parser.add_argument("outfile")
    args = parser.parse_args()

    nick = args.nickname
    chan = args.channel
    file = args.outfile

    asyncio.run(main(nick, chan, file))
