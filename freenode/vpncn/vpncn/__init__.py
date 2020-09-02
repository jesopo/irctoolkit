import asyncio, itertools, re, ssl, traceback
from typing    import Dict, List, Optional, Pattern, Set, Tuple

from irctokens import build, Line, tokenise
from ircstates import Channel, User
from ircrobots import Bot as BaseBot
from ircrobots import Server as BaseServer
from ircrobots import ConnectionParams, SASLUserPass
from ircstates.numerics import *
from ircrobots.matching import ANY, Folded, Nick, Response, SELF

from .config   import Config, load_config
from .scanners import CertScanner

CONFIG:      Config
CONFIG_PATH: str

CHANSERV = Nick("ChanServ")

class Server(BaseServer):
    def __init__(self, bot: BaseBot, name: str):
        super().__init__(bot, name)
        self._whox: Dict[str, List[str]] = {}

    async def _cs_op(self, channel: Channel) -> bool:
        await self.send(build(
            "PRIVMSG", ["ChanServ", f"OP {channel.name}"]
        ))

        try:
            await self.wait_for(Response(
                "MODE", [Folded(channel.name), "+o", SELF], source=CHANSERV,
            ), timeout=2)
        except asyncio.TimeoutError:
            return False
        else:
            return True

    async def _act(self,
            user:   User,
            chan:   Channel,
            mask:   str,
            ip:     str,
            reason: str):

        act_sets   = CONFIG.act_defaults
        act_sets_c = CONFIG.channels.get(chan.name_lower, None)
        if act_sets_c is not None:
            act_sets = act_sets_c

        act_cmds   = [CONFIG.act_sets[a] for a in act_sets]
        acts       = list(itertools.chain(*act_cmds))
        # put False (non-op) acts first
        acts.sort(key=lambda x: x[0])

        data = {
            "CHAN":   chan.name,
            "NICK":   user.nickname,
            "USER":   user.username,
            "HOST":   user.hostname,
            "MASK":   mask,
            "IP":     ip,
            "REASON": reason
        }

        remove_op = False
        last      = len(acts)-1
        for i, (need_op, action_s) in enumerate(acts):
            if need_op:
                if not "o" in chan.users[self.nickname_lower].modes:
                    got_op = await self._cs_op(chan)
                    if not got_op:
                        break
                    else:
                        remove_op = True

            action = tokenise(action_s.format(**data))
            if i == last and remove_op:
                target = self.casefold(action.params[0])
                if (action.command == "MODE" and
                        chan.name_lower == target and
                        len(action.params[2:]) < self.isupport.modes):
                    action.params[1] += "-o"
                    action.params.append(self.nickname)
                else:
                    await self.send(action)
                    action = build("MODE", [chan.name, "-o", self.nickname])
            await self.send(action)

    async def _scan(self,
            user: User,
            chan: Channel,
            host: str):
        for host_pattern, mask_template in CONFIG.host_patterns:
            match = host_pattern.search(host)
            if match:
                ip   = match.group("ip")
                mask = mask_template.format(IP=ip)

                list_modes = (
                    chan.list_modes.get("b", [])+
                    chan.list_modes.get("q", []))
                if not mask in list_modes:
                    reason = await CertScanner().scan(ip, CONFIG.bad)
                    if reason is not None:
                        await self._act(user, chan, mask, ip, reason)

    async def line_read(self, line: Line):
        global CONFIG
        print(f"{self.name} < {line.format()}")
        if   line.command == "001":
            chans = list(CONFIG.channels.keys())
            await self.send(build("JOIN", [",".join(chans)]))

        elif (line.command == "JOIN" and
                not self.is_me(line.hostmask.nickname)):
            nick = self.casefold(line.hostmask.nickname)
            chan = self.casefold(line.params[0])

            if not nick in self._whox:
                self._whox[nick] = []
            self._whox[nick].append(chan)

            await self.send(build("WHO", [nick, "%int,111"]))

        elif (line.command == RPL_WHOSPCRPL and
                line.params[1] == "111"):
            nick = self.casefold(line.params[3])
            print("whox", nick)

            if nick in self.users:
                user = self.users[nick]
                chan = self.channels[self._whox[nick][0]]
                host = line.params[2]
                if host == "255.255.255.255":
                    host = user.hostname

                await self._scan(user, chan, host)

        elif line.command == RPL_ENDOFWHO:
            nick = self.casefold(line.params[1])
            if nick in self._whox:
                print("popping", nick, self._whox[nick].pop(0))
                if not self._whox[nick]:
                    print("removing", nick)
                    del self._whox[nick]

        elif (line.command == "JOIN" and
                self.is_me(line.hostmask.nickname)):
            await self.send(build("MODE", [line.params[0], "+bq"]))

        elif (line.command == "INVITE" and
                self.is_me(line.params[0])):
            userhost = f"{line.hostmask.username}@{line.hostmask.hostname}"
            for admin_mask in CONFIG.admins:
                if admin_mask.match(userhost):
                    await self.send(build("JOIN", [line.params[1]]))
                    break

        elif (line.command == "PRIVMSG" and
                self.is_me(line.params[0]) and
                line.params[1] == "rehash"):
            userhost = f"{line.hostmask.username}@{line.hostmask.hostname}"
            for admin_mask in CONFIG.admins:
                if admin_mask.match(userhost):
                    CONFIG = load_config(CONFIG_PATH)
                    print("rehashed")
                    break

    async def line_send(self, line: Line):
        print(f"{self.name} > {line.format()}")

class Bot(BaseBot):
    def create_server(self, name: str):
        return Server(self, name)

async def main(config_path: str):
    global CONFIG, CONFIG_PATH
    CONFIG_PATH = config_path
    config      = load_config(config_path)
    CONFIG      = config

    bot = Bot()
    params = ConnectionParams(
        config.nickname,
        config.hostname,
        6697,
        True
    )
    sasl_user, sasl_pass = config.sasl
    params.sasl = SASLUserPass(sasl_user, sasl_pass)

    await bot.add_server("server", params)
    await bot.run()
