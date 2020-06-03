import asyncio, json, sys

from typing   import List
from argparse import ArgumentParser

from irctokens import build, Line
from ircrobots import Bot as BaseBot
from ircrobots import Server as BaseServer
from ircrobots import ConnectionParams

from ircstates.numerics import *
from ircrobots.matching import (Response, Responses, ANY, SELF, Folded, Regex,
    Formatless, Nick)

NICK = ""
CHAN = ""
FILE = ""

NICKSERV = Nick("NickServ")
RESP_REG   = Response("NOTICE", [SELF, Regex("^Information on ")],
    source=NICKSERV)
RESP_UNREG = Response("NOTICE", [SELF, Regex("^\\S+ is not registered.$")],
    source=NICKSERV)
RESP_END   = Response("NOTICE", [SELF, Formatless("*** End of Info ***")],
    source=NICKSERV)

class Server(BaseServer):
    async def line_read(self, line: Line):
        if line.command == "001":
            await self.send(build("MODE", [CHAN, "+b"]))

            masks: List[str] = []
            while True:
                line = await self.wait_for(Responses(
                    [RPL_BANLIST, RPL_ENDOFBANLIST],
                    [ANY, Folded(CHAN), ANY]
                ))
                if line.command == RPL_BANLIST:
                    masks.append(line.params[2])
                else:
                    break

            accounts: List[str] = []
            for mask in masks:
                if mask.startswith("$a:"):
                    accounts.append(mask.split(":", 1)[1])

            states: Dict[str, bool] = {}
            for account in accounts:
                await self.send(build("NS", ["INFO", account]))
                line = await self.wait_for({
                    RESP_REG, RESP_UNREG
                })

                if line.params[1].startswith("Information on "):
                    states[account] = True
                    await self.wait_for(RESP_END)
                else:
                    states[account] = False
            with open(FILE, "w") as outfile:
                outfile.write(json.dumps(states, indent=4, sort_keys=True))
                outfile.write("\n")
            print(f"! written to {FILE}")
            sys.exit()

    def line_preread(self, line: Line):
        print(f"{self.name} < {line.format()}")
    def line_presend(self, line: Line):
        print(f"{self.name} > {line.format()}")

class Bot(BaseBot):
    def create_server(self, name: str):
        return Server(self, name)

async def main():
    bot = Bot()
    params = ConnectionParams(NICK, "chat.freenode.net", 6697, True)
    server = await bot.add_server("freenode", params)
    await bot.run()

if __name__ == "__main__":
    parser = ArgumentParser(
        description="Find expired/deleted/etc accounts on freenode banlist")
    parser.add_argument("nickname")
    parser.add_argument("channel")
    parser.add_argument("outfile")
    args = parser.parse_args()

    NICK = args.nickname
    CHAN = args.channel
    FILE = args.outfile

    asyncio.run(main())
