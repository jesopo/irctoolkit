import asyncio

from typing import List, Optional, Tuple

from irctokens import build, Line
from ircrobots import Bot as BaseBot
from ircrobots import Server as BaseServer
from ircrobots import ConnectionParams, SASLUserPass

from ircstates.numerics import *
from ircrobots.matching import Responses, SELF, Folded

from ircrobots.glob import compile as glob_compile

class Server(BaseServer):
    async def _ban_list(self,
            chan: str,
            depth=0
            ) -> List[Tuple[(List[str], str, int)]]:

        await self.send(build("MODE", [chan, "+b"]))

        masks = []
        while True:
            line = await self.wait_for(Responses(
                [RPL_BANLIST, RPL_ENDOFBANLIST],
                [SELF, Folded(chan)]
            ))

            if line.command == RPL_ENDOFBANLIST:
                break
            else:
                mask   = line.params[2]
                set_by = line.params[3]
                set_at = int(line.params[4])
                masks.append(([mask], set_by, set_at))

        if depth == 0:
            for (mask,), _, _ in list(masks):
                if mask.startswith("$j:"):
                    nextchan = mask.split(":", 1)[1]
                    nextchan_masks = await self._ban_list(nextchan, depth + 1)
                    for nextmask, set_by, set_at in nextchan_masks:
                        masks.append((nextmask + [mask], set_by, set_at))

        return masks

    def _masks(self,
            nickname: str,
            username: str,
            hostname: str,
            realname: str,
            account: Optional[str]):
        masks = []

        hostmask = self.casefold(f"{nickname}!{username}@{hostname}")
        masks.append(hostmask)

        freal = self.casefold(realname)
        masks.append(f"$x:{hostmask}#{freal}")
        masks.append(f"$r:{freal}")

        if account is not None:
            masks.append(self.casefold(f"$a:{account}"))
        else:
            masks.append("$~a")
        return masks

    async def _find_user(self, nick: str
            ) -> Optional[Tuple[(str, str, str, str, Optional[str])]]:
        nick_fold = self.casefold(nick)
        if nick_fold in self.users:
            user = self.users[nick_fold]
            return (
                user.nickname,
                user.username or "",
                user.hostname or "",
                user.realname or "",
                user.account)

        whois = await self.send_whois(nick)
        if whois is not None:
            return (
                whois.nickname,
                whois.username or "",
                whois.hostname or "",
                whois.realname or "",
                whois.account)

        return None

    async def _cmodes(self, chan: str) -> Optional[str]:
        chan_fold = self.casefold(chan)
        if chan_fold in self.channels:
            channel = self.channels[chan_fold]
            return "".join(channel.modes.keys())

        await self.send(build("MODE", [chan]))
        line = await self.wait_for(Responses(
            [RPL_CHANNELMODEIS, ERR_NOSUCHCHANNEL],
            [SELF, Folded(chan)]
        ))

        if line.command == RPL_CHANNELMODEIS:
            return line.params[2].replace("+", "")

        return None

    async def line_read(self, line: Line):
        print(f"< {line.format()}")

        if (line.command == "PRIVMSG" and
                self.is_me(line.params[0]) and
                not self.is_me(line.hostmask.nickname)):

            argv    = list(filter(bool, line.params[1].split(" ")))
            command = argv.pop(0).upper()
            sender  = line.hostmask.nickname

            if command == "CANTJOIN":
                if not len(argv) > 1:
                    await self.send(build(
                        "NOTICE", [sender, "not enough params"]
                    ))
                    return

                nick      = argv[0]
                nick_info = await self._find_user(nick)
                if nick_info is None:
                    await self.send(build(
                        "NOTICE", [sender, f"user {nick} not found"]
                    ))
                    return

                chan      = argv[1]
                chan_bans = await self._ban_list(chan)

                cased_nick, user, host, real, acc = nick_info
                nick_masks = self._masks(nick, user, host, real, acc)

                reasons = []

                cmodes = await self._cmodes(chan)
                if cmodes is not None:
                    if "r" in cmodes and acc is None:
                        reasons.append("cmode +r")

                for mask_tree, set_by, set_at in chan_bans:
                    mask = mask_tree[0]
                    glob = glob_compile(self.casefold(mask))

                    for nick_mask in nick_masks:
                        if mask[0] == "$" and not nick_mask[0] == "$":
                            pass
                        elif glob.match(nick_mask):
                            reason = f"ban on {mask}"
                            if mask_tree[1:]:
                                reason += f" ({mask_tree[1]})"
                            reasons.append(reason)

                if reasons:
                    out = f"{cased_nick} cannot join {chan} because: "
                    out += ", ".join(reasons)
                    await self.send(build("NOTICE", [sender, out]))
                else:
                    await self.send(build("NOTICE", [sender, "idk"]))

    async def line_send(self, line: Line):
        print(f"> {line.format()}")


class Bot(BaseBot):
    def create_server(self, name: str):
        return Server(self, name)


async def main(
        nick: str,
        sasl: Optional[str]=None):

    bot = Bot()

    sasl_params: Optional[SASLUserPass] = None
    if sasl:
        account, _, password = sasl.partition(":")
        sasl_params = SASLUserPass(account, password)

    params = ConnectionParams(
        nick,
        username=nick,
        realname="irctoolkit cantjoin v1",
        host    ="chat.freenode.net",
        port    =6697,
        tls     =True,
        sasl    =sasl_params)

    await bot.add_server("freenode", params)
    await bot.run()
