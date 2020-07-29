import asyncio

from enum import IntEnum
from typing import List, Optional, Set, Tuple

from irctokens import build, Line
from ircrobots import Bot as BaseBot
from ircrobots import Server as BaseServer
from ircrobots import ConnectionParams, SASLUserPass

from ircstates.numerics import *
from ircrobots.matching import Responses, SELF, Folded

from ircrobots.glob import compile as glob_compile

class Type(IntEnum):
    BAN   = 1
    QUIET = 2

class Server(BaseServer):
    async def _ban_list(self,
            chan:  str,
            modes: str,
            depth=0
            ) -> Optional[List[Tuple[Type, List[str], str, int]]]:

        await self.send(build("MODE", [chan, f"+{modes}"]))

        ends = len(modes)
        masks: List[Tuple[Type, List[str], str, int]] = []
        while True:
            line = await self.wait_for(Responses([
                RPL_BANLIST, RPL_QUIETLIST,
                RPL_ENDOFBANLIST, RPL_ENDOFQUIETLIST, ERR_NOSUCHCHANNEL
            ], [SELF, Folded(chan)]))

            if line.command == ERR_NOSUCHCHANNEL:
                return None
            elif line.command in [RPL_ENDOFBANLIST, RPL_ENDOFQUIETLIST]:
                ends -= 1
                if ends == 0:
                    break
            else:
                offset = 0
                type = Type.BAN
                if line.command == RPL_QUIETLIST:
                    offset += 1
                    type = Type.QUIET
                mask   = line.params[offset+2]
                set_by = line.params[offset+3]
                set_at = int(line.params[offset+4])
                masks.append((type, [mask], set_by, set_at))

        if depth == 0:
            for type, (mask,), _, _ in list(masks):
                if mask.startswith("$j:"):
                    nextchan = mask.split(":", 1)[1].split("$", 1)[0]
                    nextchan_masks = await self._ban_list(
                        nextchan, "b", depth + 1
                    )
                    if nextchan_masks is not None:
                        for _, nextmask, set_by, set_at in nextchan_masks:
                            masks.append(
                                (type, nextmask+[mask], set_by, set_at)
                            )

        return masks

    def _masks(self,
            nickname: str,
            username: str,
            hostname: str,
            realname: str,
            account: Optional[str]):
        masks: List[Tuple[bool, str]] = []

        hostmask = self.casefold(f"{nickname}!{username}@{hostname}")
        masks.append((False, hostmask))

        freal = self.casefold(realname)
        masks.append((True, f"$x:{hostmask}#{freal}"))
        masks.append((True, f"$r:{freal}"))

        if account is not None:
            facc = self.casefold(account)
            masks.append((True, f"$a:{facc}"))
            masks.append((True, "$a"))
        else:
            masks.append((True, "$~a"))
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

    def _prepare_mask(self, mask: str) -> Tuple[bool, str]:
        if ":" in mask:
            ext, sep, mask = mask.partition(":")
        else:
            ext = ""
            sep = ""

        if "$" in mask:
            # cut off banforward
            mask = mask.split("$", 1)[0]

        return bool(sep), ext + sep + self.casefold(mask)

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
                chan_bans = await self._ban_list(chan, "b")
                if chan_bans is None:
                    await self.send(build(
                        "NOTICE", [sender, f"channel {chan} not found"]
                    ))
                    return

                cased_nick, user, host, real, acc = nick_info
                user_masks = self._masks(nick, user, host, real, acc)

                reasons = []

                cmodes = await self._cmodes(chan)
                if cmodes is not None:
                    if "r" in cmodes and acc is None:
                        reasons.append("cmode +r")

                for _, mask_tree, set_by, set_at in chan_bans:
                    raw_mask          = mask_tree[0]
                    chan_extban, mask = self._prepare_mask(raw_mask)

                    glob = glob_compile(mask)

                    for user_extban, user_mask in user_masks:
                        if (chan_extban == user_extban and
                                glob.match(user_mask)):
                            reason = f"ban on {raw_mask}"
                            if mask_tree[1:]:
                                reason += f" ({mask_tree[1]})"
                            reasons.append(reason)

                if reasons:
                    out = f"{cased_nick} cannot join {chan} because: "
                    out += ", ".join(reasons)
                    await self.send(build("NOTICE", [sender, out]))
                else:
                    await self.send(build("NOTICE", [sender, "idk"]))
            elif command == "DUPES":
                if not len(argv) > 0:
                    await self.send(build(
                        "NOTICE", [sender, "not enough params"]
                    ))
                    return

                query     = "bq"
                chan      = argv[0]
                chan_bans = await self._ban_list(chan, query)
                if chan_bans is None:
                    await self.send(build(
                        "NOTICE", [sender, f"channel {chan} not found"]
                    ))
                    return

                seen:       Set[Tuple[Type, str]] = set()
                duplicates: List[Tuple[Type, List[str]]] = []
                for type, mask_tree, set_by, set_at in chan_bans:
                    raw_mask     = mask_tree[0]
                    extban, mask = self._prepare_mask(raw_mask)

                    key = (type, mask)
                    if key in seen:
                        duplicates.append((type, mask_tree))
                    else:
                        seen.add(key)

                if duplicates:
                    outs: List[str] = [f"duplicates on {chan}: "]
                    for type, mask_tree in duplicates:
                        mode = ""
                        if len(query) > 1:
                            if type == Type.QUIET:
                                mode = "+q "
                            else:
                                mode = "+b "

                        out = f"{mode}{mask_tree[0]} ({mask_tree[1]}), "
                        if (len(outs[-1])+len(out)) > 400:
                            outs[-1] = outs[-1][:-1]
                            outs.append(out)
                        else:
                            outs[-1] = outs[-1] + out
                    outs[-1] = outs[-1][:-2]

                    for out in outs:
                        await self.send(build("NOTICE", [sender, out]))
                else:
                    await self.send(build(
                        "NOTICE", [sender, f"no duplicates found for {chan}"]
                    ))
                    return

    async def line_send(self, line: Line):
        print(f"> {line.format()}")


class Bot(BaseBot):
    def create_server(self, name: str):
        return Server(self, name)


async def main(
        nick: str,
        sasl: Optional[str]=None):

    bot = Bot()

    params = ConnectionParams(
        nick,
        username=nick,
        realname="irctoolkit cantjoin v1",
        host    ="chat.freenode.net",
        port    =6697,
        tls     =True)

    if sasl:
        account, _, password = sasl.partition(":")
        params.sasl = SASLUserPass(account, password)

    await bot.add_server("freenode", params)
    await bot.run()
