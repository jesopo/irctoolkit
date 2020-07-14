from argparse     import ArgumentParser
from asyncio      import run
from configparser import ConfigParser
from os.path      import expanduser
from . import main

if __name__ == '__main__':
    parser = ArgumentParser(
        description="Bot for freenode to track known baddies")

    parser.add_argument("config")
    args = parser.parse_args()

    config = ConfigParser()
    config.read(args.config)

    nickname   = config["bot"]["nickname"]
    sasl       = config["bot"]["sasl"]
    database   = expanduser(config["bot"]["database"])
    log_chan   = config["bot"]["log-chan"]
    watch_chan = config["bot"]["watch-chan"]

    run(main(database, nickname, sasl, log_chan, watch_chan))
