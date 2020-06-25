import asyncio, sys

from typing   import Any, Dict, List, Optional, Tuple
from argparse import ArgumentParser

import yaml

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
    async def _ban_list(self,
            chan: str,
            depth=0
            ) -> Optional[List[Tuple[(List[str], str, int)]]]:

        await self.send(build("MODE", [chan, "+b"]))

        masks: List[Tuple[List[str], str, int]] = []
        while True:
            line = await self.wait_for(Responses(
                [RPL_BANLIST, RPL_ENDOFBANLIST, ERR_NOSUCHCHANNEL],
                [SELF, Folded(chan)]
            ))

            if line.command == ERR_NOSUCHCHANNEL:
                return None
            elif line.command == RPL_ENDOFBANLIST:
                break
            else:
                mask   = line.params[2]
                set_by = line.params[3]
                set_at = int(line.params[4])
                masks.append(([mask], set_by, set_at))

        if depth == 0:
            for (mask,), _, _ in list(masks):
                if mask.startswith("$j:"):
                    nextchan = mask.split(":", 1)[1].split("$", 1)[0]
                    nextchan_masks = await self._ban_list(nextchan, depth + 1)
                    if nextchan_masks is not None:
                        for nextmask, set_by, set_at in nextchan_masks:
                            masks.append((nextmask+[mask], set_by, set_at))

        return masks

    async def line_read(self, line: Line):
        if line.command == "001":
            await self.send(build("MODE", [CHAN, "+b"]))

            chan_bans = await self._ban_list(CHAN)
            if chan_bans is None:
                sys.stderr.write(f"{CHAN} not found\n")
                sys.exit(1)

            accounts: Dict[str, List[str]] = {}
            for mask_tree, set_by, set_at in chan_bans:
                mask = mask_tree[0]
                if mask.startswith("$a:"):
                    account = mask.split(":", 1)[1].split("$", 1)[0]
                    account = self.casefold(account)
                    if not account in accounts:
                        accounts[account] = []

                    accounts[account].append((mask_tree[1:] or [CHAN])[0])

            states: Dict[str, bool] = {}
            for account in accounts.keys():
                await self.send(build("NS", ["INFO", account]))
                line = await self.wait_for({
                    RESP_REG, RESP_UNREG
                })

                if line.params[1].startswith("Information on "):
                    states[account] = True
                    await self.wait_for(RESP_END)
                else:
                    states[account] = False

            states_where: Dict[str, Any] = {}
            for account in sorted(accounts.keys()):
                state = {
                    "registered": states[account],
                    "sources":    accounts[account]
                }
                states_where[account] = state

            with open(FILE, "w") as outfile:
                outfile.write(
                    yaml.dump(states_where)
                )
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
