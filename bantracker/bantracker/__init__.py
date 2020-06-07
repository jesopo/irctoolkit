import asyncio, os
import pendulum

from argparse     import ArgumentParser
from configparser import ConfigParser
from dataclasses  import dataclass
from enum         import IntEnum
from typing       import Dict, Iterable, List, Optional, Set, Tuple

from irctokens import build, Hostmask, Line
from ircstates import Channel, User, ChannelUser
from ircrobots import Bot as BaseBot
from ircrobots import Server as BaseServer
from ircrobots import ConnectionParams, SASLUserPass

from ircstates.numerics import *
from ircrobots.glob     import compile as glob_compile
from ircrobots.glob     import Glob
from ircrobots.matching import Response, Responses, ANY, Folded, Nick, SELF

from .utils    import from_pretty_time
from .config   import BotConfig, ChannelConfig, ChannelConfigs
from .database import BanDatabase

class Types(IntEnum):
    BAN   = 1
    QUIET = 2

DATA:         str
DB:           BanDatabase
CONFIG:       BotConfig
CHAN_CONFIGS: ChannelConfigs

CHANSERV = Nick("ChanServ")
ENFORCE_REASON = "User is banned from this channel ({id})"

class Server(BaseServer):
    async def _assure_op(self, channel: Channel) -> bool:
        channel_self = channel.users[self.nickname_lower]
        if not "o" in channel_self.modes:
            await self.send(build(
                "PRIVMSG", ["ChanServ", f"OP {channel.name}"]
            ))
            await self.wait_for(Response(
                "MODE", [Folded(channel.name), "+o", SELF], source=CHANSERV
            ))
            return True
        else:
            return False

    def _mode_batches(self,
            chunk_n: int,
            add:     bool,
            modes:   str,
            args:    List[str]
            ) -> Iterable[Tuple[str, List[str]]]:

        mod = "+" if add else "-"
        for i in range(0, len(modes), chunk_n):
            cur_slice = slice(i, i+chunk_n)
            cur_modes = modes[cur_slice]
            cur_args  =  args[cur_slice]
            yield f"{mod}{modes[cur_slice]}", args[cur_slice]

    async def _remove_modes(self,
            channel:   Channel,
            modes:     str,
            args:      List[str],
            remove_op: bool):

        if remove_op:
            modes += "o"
            args.append(self.nickname)

        batches = self._mode_batches(
            self.isupport.modes, False, modes, args
        )
        for b_modes, b_args in batches:
            await self.send(build("MODE", [channel.name, b_modes]+b_args))

    async def _mode_list(self,
            channel: str,
            modes:   str
            ) -> List[Tuple[int, str, str, int]]:

        await self.send(build("MODE", [channel, f"+{modes}"]))

        waiting = len(modes)

        masks: List[Tuple[int, str, str, int]] = []
        while True:
            line = await self.wait_for(Responses([
                RPL_BANLIST, RPL_ENDOFBANLIST,
                RPL_QUIETLIST, RPL_ENDOFQUIETLIST
            ], [ANY, Folded(channel)]))
            if line.command in [RPL_ENDOFBANLIST, RPL_ENDOFQUIETLIST]:
                waiting -= 1
                if waiting == 0:
                    break
            else:
                # :server 367 * #c mask set-by set-at
                # :server 728 * q #c mask set-by set-at
                offset = 0
                type = Types.BAN
                if line.command == RPL_QUIETLIST:
                    offset += 1
                    type = Types.QUIET

                mask   = line.params[offset+2]
                set_by = line.params[offset+3]
                set_at = int(line.params[offset+4])
                masks.append((type, mask, set_by, set_at))
        return masks

    async def _check_expires(self):
        now = pendulum.now("utc")
        expired = DB.get_before(now.timestamp())
        expired_groups: Dict[str, List[Tuple[int, str]]] = {}
        for channel, type, mask in expired:
            if not channel in expired_groups:
                expired_groups[channel] = []
            expired_groups[channel].append((type, mask))

        for channel_name, type_masks in expired_groups.items():
            if channel_name in self.channels:
                channel = self.channels[channel_name]
                remove_op = False
                if CONFIG.chanserv:
                    remove_op = await self._assure_op(channel)

                modes = ""
                args: List[str] = []
                for type, mask in type_masks:
                    if   type == Types.BAN:
                        modes += "b"
                    elif type == Types.QUIET:
                        if CONFIG.quiet is not None:
                            modes += CONFIG.quiet
                        else:
                            continue
                    args.append(mask)
                await self._remove_modes(channel, modes, args, remove_op)

    def _has_permission(self,
            ban_id: int,
            set_by: str,
            ban_channel: str,
            line: Line) -> bool:
        target = self.casefold(line.params[0])
        if (line.source is not None and
                self.casefold(line.source) == self.casefold(set_by)):
            return True
        elif (target in self.channels and
                self.casefold(target) == ban_channel):
            channel  = self.channels[target]
            nickname = self.casefold(line.hostmask.nickname)
            if (nickname in channel.users and
                    "o" in channel.users[nickname].modes):
                return True
        return False

    def _channel_masks(self,
            users:   List[User],
            extbans: List[str]
            ) -> Iterable[Tuple[str, User]]:
        for user in users:
            # XXX or is for fixing an ircstates incorrect return hint
            yield (user.hostmask() or "", user)

            vars = {
                "account":  user.account or "",
                "hostmask": user.hostmask(),
                "realname": user.realname
            }
            for extban in extbans:
                formatted = extban.format(**vars)
                yield (formatted, user)

    async def line_read(self, line: Line):
        if line.command == RPL_WELCOME:
            # we have successfully connected - join all our channels!
            for i in range(0, len(CONFIG.channels), 10):
                # (split our JOINs in to groups of 10)
                channel_str = ",".join(CONFIG.channels[i:i+10])
                await self.send(build("JOIN", [channel_str]))

        elif line.command == "PONG" and line.params[-1] == "expirecheck":
            await self._check_expires()

        elif (line.command == "JOIN" and
                self.is_me(line.hostmask.nickname)):
            channel = self.channels[self.casefold(line.params[0])]

            tracked_masks = DB.get_existing(channel.name_lower)

            mode_query = "b" + (CONFIG.quiet or "")
            current_masks = list(await self._mode_list(
                channel.name_lower, mode_query
            ))

            tracked_masks_set = set((m[0], m[1]) for m in tracked_masks)
            current_masks_set = set((m[0], m[1]) for m in current_masks)

            now = int(pendulum.now("utc").timestamp())

            # which bans/quiets were removed while we weren't watching
            for type, mask in tracked_masks:
                if not (type, mask) in current_masks_set:
                    DB.set_removed(channel.name_lower, type, mask, None, now)
            # which bans/quiets were added while we weren't watching
            for type, mask, set_by, set_at in current_masks:
                if not (type, mask) in tracked_masks_set:
                    DB.add(channel.name_lower, type, mask, set_by, set_at)

        elif (line.command == "MODE" and
                line.source is not None and
                self.has_channel(line.params[0])):
            channel = self.channels[self.casefold(line.params[0])]

            args = line.params[2:]
            modes: List[Tuple[str, str]] = []
            modifier = "+"

            watch_modes = "b"
            if CONFIG.quiet is not None:
                watch_modes += CONFIG.quiet

            # tokenise out the MODE change....
            for c in str(line.params[1]):
                if c in ["+", "-"]:
                    modifier = c
                elif c in watch_modes and args:
                    modes.append((f"{modifier}{c}", args.pop(0)))

            now = int(pendulum.now("utc").timestamp())
            maybe_enforce: List[Tuple[int, int, Glob]] = []
            for mode, arg in modes:
                type = Types.BAN if mode[1] == "b" else Types.QUIET
                # this could be a +b or a -b for an existing mask.
                # either way, we want to expire any previous instances of it
                DB.set_removed(channel.name_lower, type, arg, line.source, now)

                if mode[0] == "+":
                    # a new ban or quiet! lets track it
                    ban_id = DB.add(
                        channel.name_lower, type, arg, line.source, now
                    )
                    await self._notify(
                        channel.name, line.hostmask.nickname, ban_id
                    )

                    compiled = glob_compile(arg)
                    maybe_enforce.append((type, ban_id, compiled))

            # whether or not to remove people affected by new bans
            c_enforce = CHAN_CONFIGS.get(channel.name_lower)
            if maybe_enforce and (
                    (c_enforce is None and CONFIG.enforce) or c_enforce):

                # all nicks in a channel
                nicks = list(channel.users.keys())
                # (except for me)
                nicks.remove(self.nickname_lower)
                # get all users and all their hostmasks (and extbans!)
                users = [self.users[n] for n in nicks]
                user_masks = self._channel_masks(users, CONFIG.extbans)

                kicks:    List[Tuple[User, int]] = []
                devoices: List[User] = []
                # compile mask and test against each user
                for user_mask, user in user_masks:
                    cuser = channel.users[user.nickname_lower]
                    for type, ban_id, compiled in maybe_enforce:
                        if compiled.match(user_mask):
                            if (type == Types.BAN and
                                    not cuser.modes):
                                kicks.append((user, ban_id))
                            elif (type == Types.QUIET and
                                    andcuser.modes == ["v"]):
                                devoices.append(user)

                if kicks or devoices:
                    remove_op = False
                    if CONFIG.chanserv:
                        remove_op = await self._assure_op(channel)

                    # non-status users covered by a new ban
                    for user, ban_id in kicks:
                        reason = ENFORCE_REASON.format(id=ban_id)
                        await self.send(build(
                            "KICK", [channel.name, user.nickname, reason]
                        ))

                    # +v users covered by a new quiet
                    rem_modes = ""
                    rem_args: List[str] = []
                    for user in devoices:
                        rem_modes += "v"
                        rem_args.append(user.nickname)

                    await self._remove_modes(
                        channel, rem_modes, rem_args, remove_op
                    )

        elif (line.command == "PRIVMSG" and
                line.source is not None):
            trigger = CONFIG.trigger
            if self.is_channel(line.params[0]):
                chan_config = CHAN_CONFIGS.get(self.casefold(line.params[0]))
                if chan_config.trigger is not None:
                    trigger = chan_config.trigger

            message = line.params[1]
            command, _, message = message.partition(" ")
            command = command.lower()

            if command == f"{trigger}set":
                target = self.casefold(line.params[0])
                if not target in self.channels:
                    # this command must be used in-channel
                    raise Exception()

                channel  = self.channels[target]
                nickname = self.casefold(line.hostmask.nickname)
                cuser    = channel.users[nickname]
                if not "o" in cuser.modes:
                    # you do not have permission to do this
                    raise Exception()

                key, _, value = message.strip().partition(" ")
                if not key and value:
                    # please provide a key and value
                    raise Exception()

                chan_config = CHAN_CONFIGS.get(target)
                try:
                    set_value = chan_config.set(key, value)
                except KeyError:
                    # unknown setting
                    raise Exception()

                CHAN_CONFIGS.set(target)
                out = f"Set {key} '{set_value}' for {channel.name}"
                await self.send(build("NOTICE", [line.hostmask.nickname, out]))

            elif command == f"{trigger}comment":
                ban_id_s, _, message = message.partition(" ")
                ban_id = -1
                if ban_id_s == "^" and self.is_channel(line.params[0]):
                    channel_name = self.casefold(line.params[0])
                    last_ban_id = DB.get_last(channel_name)
                    if last_ban_id is None:
                        # no last ban id for channel
                        raise Exception()
                    ban_id = last_ban_id
                elif not ban_id_s.isdigit():
                    # please provide a numeric ban id
                    raise Exception()
                else:
                    ban_id = int(ban_id_s)

                    if not DB.ban_exists(ban_id):
                        # ban does not exist
                        raise Exception()

                ban_channel, type, mask, set_by, _, _2 = DB.get_ban(ban_id)

                if not self._has_permission(ban_id, set_by, ban_channel, line):
                    # you do not have permission to do this
                    raise Exception()

                if not message.strip():
                    # please provide duration or reason or both
                    raise Exception()

                duration = -1
                if message[0] == "+":
                    duration_s, _, message = message[1:].partition(" ")
                    maybe_duration = from_pretty_time(duration_s)
                    if maybe_duration is None:
                        # invalid duration provided
                        raise Exception()
                    duration = maybe_duration
                reason = message.strip()

                now = int(pendulum.now("utc").timestamp())

                outs: List[str] = []
                if len(reason):
                    DB.set_reason(ban_id, line.source, now, reason)
                    outs.append("reason")
                if duration > -1:
                    DB.set_duration(ban_id, line.source, now, duration)
                    outs.append("duration")

                out = " and ".join(outs)
                type_s = Types(type).name.lower()
                out = f"Set {out} for {type_s} {ban_id} ({mask})"
                await self.send(build("NOTICE", [line.hostmask.nickname, out]))

    async def _notify(self, channel: str, set_by: str, ban_id: int):
        out = f"Ban {ban_id} added for {channel}"
        await self.send(build("NOTICE", [set_by, out]))

    def line_preread(self, line: Line):
        print(f"{self.name} < {line.format()}")
    def line_presend(self, line: Line):
        print(f"{self.name} > {line.format()}")

class Bot(BaseBot):
    def create_server(self, name: str):
        return Server(self, name)

async def main(
        params: ConnectionParams,
        config: BotConfig):
    bot = Bot()
    await bot.add_server(params.host, params)

    global CONFIG
    CONFIG = config

    global CHAN_CONFIGS
    chan_config_dir = os.path.join(config.data, "channels")
    CHAN_CONFIGS    = ChannelConfigs(chan_config_dir)

    global DB
    db_file = os.path.join(config.data, "bantracker.db")
    DB      = BanDatabase(db_file)

    async def _expire_timer():
        while True:
            now = pendulum.now("utc")
            until_minute = 60-now.second
            await asyncio.sleep(until_minute)

            if bot.servers:
                server = bot.servers[params.host]
                await server.send(build("PING", ["expirecheck"]))
    asyncio.create_task(_expire_timer())

    await bot.run()

def _main():
    parser = ArgumentParser(description="An IRC ban tracking bot")
    parser.add_argument("config")
    args = parser.parse_args()

    # read out the config file
    config_obj = ConfigParser()
    config_obj.read(args.config)
    config = dict(config_obj["bot"])

    host, _, port_str   = config["host"].partition(":")
    tls  = True
    port = 6697
    if port_str:
        _, tls_symbol, port = port_str.rpartition("+")
        port = int(port)
        tls  = bool(tls_symbol)

    tls_verify = config.get("tls_verify", "yes") == "yes"
    bindhost   = config.get("bind", None)

    params = ConnectionParams(
        config["nick"],
        host,
        port,
        tls,
        tls_verify = tls_verify,
        bindhost   = bindhost
    )
    if "sasl" in config:
        sasl_user, _, sasl_pass = config["sasl"].partition(":")
        params.sasl = SASLUserPass(sasl_user, sasl_pass)

    data = os.path.expanduser(config["data"])
    if not os.path.isdir(data):
        os.makedirs(data)

    extbans_s = config.get("extbans", "")
    extbans_l = [e.strip() for e in extbans_s.split(",")]
    extbans = list(filter(bool, extbans_l))
    # grab db filename and list of channels to join
    bot_config = BotConfig(
        data,
        [c.strip() for c in config["channels"].split(",")],
        config.get("chanserv", "no") == "yes",
        config.get("enforce", "no") == "yes",
        extbans,
        config.get("trigger", "!"),
        config.get("quiet", None)
    )

    asyncio.run(main(params, bot_config))
