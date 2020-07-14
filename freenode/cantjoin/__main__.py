from argparse     import ArgumentParser
from asyncio      import run
from configparser import ConfigParser
from . import main

if __name__ == '__main__':
    parser = ArgumentParser(
        description="Bot for freenode to detect JOIN preventers")

    parser.add_argument("config")
    args = parser.parse_args()

    config = ConfigParser()
    config.read(args.config)

    nickname = config["bot"]["nickname"]
    sasl     = config["bot"]["sasl"]

    run(main(nickname, sasl))
