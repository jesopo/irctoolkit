import asyncio, os.path
import pendulum

from argparse     import ArgumentParser
from configparser import ConfigParser
from dataclasses  import dataclass
from enum         import IntEnum
from typing       import Dict, List, Optional, Set, Tuple

from irctokens import build, Hostmask, Line
from ircstates import User
from ircrobots import Bot as BaseBot
from ircrobots import Server as BaseServer
from ircrobots import ConnectionParams, SASLUserPass

from ircstates.numerics import *
from ircrobots.glob     import compile as glob_compile
from ircrobots.glob     import Glob
from ircrobots.matching import Response, Responses, ANY, Folded, Nick, SELF

from .utils    import from_pretty_time
from .obj      import Config, Types
from .database import BanDatabase

DB:     BanDatabase
CONFIG: Config

CHANSERV = Nick("ChanServ")
ENFORCE_REASON = "User is banned from this channel ({id})"

class Server(BaseServer):
    async def _assure_op(self, channel) -> bool:
        channel_self = channel.users[self.nickname_lower]
        if not "o" in channel_self.modes and CONFIG.chanserv:
            await self.send(build("CS", ["OP", channel.name]))
            await self.wait_for(
                Response(
                    "MODE",
                    [Folded(channel.name), "+o", SELF],
                    source=CHANSERV
                )
            )
            return True
        else:
            return False

    async def _remove_modes(self,
            channel_name: str,
            type_masks:   List[Tuple[int, str]]):

        if channel_name in self.channels:
            channel   = self.channels[channel_name]
            remove_op = await self._assure_op(channel)

            modes = ""
            args: List[str] = []
            for type, mask in type_masks:
                if type   == Types.BAN:
                    modes += "b"
                elif type == Types.QUIET:
                    if CONFIG.quiet is not None:
                        modes += CONFIG.quiet
                    else:
                        continue
                args.append(mask)

            if remove_op:
                modes += "o"
                args.append(self.nickname)

            chunk_n = self.isupport.modes
            for i in range(0, len(modes), chunk_n):
                mode_str  = modes[i:i+chunk_n]
                mode_args =  args[i:i+chunk_n]
                await self.send(build(
                    "MODE",
                    [channel_name, f"-{mode_str}"]+mode_args
                ))

    async def _mode_list(self,
            channel: str,
            quiet_mode: Optional[str]) -> List[Tuple[int, str, str, int]]:
        mode_query = "b"
        if quiet_mode is not None:
            mode_query += quiet_mode
        await self.send(build("MODE", [channel, f"+{mode_query}"]))

        masks: List[Tuple[int, str, str, int]] = []
        done = 0
        while True:
            line = await self.wait_for(Responses(
                [
                    RPL_BANLIST, RPL_ENDOFBANLIST,
                    RPL_QUIETLIST, RPL_ENDOFQUIETLIST
                ],
                [ANY, Folded(channel)]
            ))
            if line.command in [RPL_ENDOFBANLIST, RPL_ENDOFQUIETLIST]:
                done += 1
                if done == len(mode_query):
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

        for channel, type_masks in expired_groups.items():
            await self._remove_modes(channel, type_masks)

    def _has_permission(self,
            ban_id: int,
            set_by: str,
            ban_channel: str,
            line: Line) -> bool:
        target = self.casefold(line.params[0])
        if self.casefold(line.source) == self.casefold(set_by):
            return True
        elif (target in self.channels and
                self.casefold(target) == ban_channel):
            channel  = self.channels[target]
            nickname = self.casefold(line.hostmask.nickname)
            if (nickname in channel.users and
                    "o" in channel.users[nickname].modes):
                return True
        return False

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
            channel = self.casefold(line.params[0])

            tracked_masks: List[Tuple[int, str]] = []
            for ban_mask in DB.get_existing(channel, Types.BAN):
                tracked_masks.append((Types.BAN, ban_mask))
            for quiet_mask in DB.get_existing(channel, Types.QUIET):
                tracked_masks.append((Types.QUIET, quiet_mask))
            tracked_masks_set = set(f"{m[0]}-{m[1]}" for m in tracked_masks)

            current_masks = await self._mode_list(channel, CONFIG.quiet)
            current_masks_set = set(f"{m[0]}-{m[1]}" for m in current_masks)

            now = int(pendulum.now("utc").timestamp())

            # which bans/quiets were removed while we weren't watching
            for type, mask in tracked_masks:
                if not f"{type}-{mask}" in current_masks_set:
                    DB.set_removed(channel, type, mask, None, now)
            # which bans/quiets were added while we weren't watching
            for type, mask, set_by, set_at in current_masks:
                if not f"{type}-{mask}" in tracked_masks_set:
                    DB.add(channel, type, mask, set_by, set_at)

        elif (line.command == "MODE" and
                line.source is not None and
                self.has_channel(line.params[0])):
            channel_name = self.casefold(line.params[0])

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
            ban_adds: List[Tuple[int, Glob]] = []
            our_hostmask = f"{self.nickname}!{self.username}@{self.hostname}"
            for mode, arg in modes:
                type = Types.BAN if mode[1] == "b" else Types.QUIET
                # this could be a +b or a -b for an existing mask.
                # either way, we want to expire any previous instances of it
                DB.set_removed(channel_name, type, arg, line.source, now)

                if mode[0] == "+":
                    # a new ban or quiet! lets track it
                    ban_id = DB.add(channel_name, type, arg, line.source, now)
                    await self._notify(
                        channel_name, line.hostmask.nickname, ban_id
                    )

                    if type == Types.BAN:
                        # this is a ban - we might want to enforce it
                        compiled = glob_compile(arg)
                        ban_adds.append((ban_id, compiled))

            # whether or not to remove people affected by new bans
            if ban_adds and CONFIG.enforce:
                channel = self.channels[channel_name]

                # get hostmask for every non-status user
                users: List[User] = []
                for nickname in channel.users:
                    # don't kick +v/+o/foo
                    if (not channel.users[nickname].modes and
                            # don't kick ourselves
                            not nickname == self.nickname_lower):
                        user = self.users[nickname]
                        users.append(user)
                user_masks = {u.hostmask(): u for u in users}

                affected: List[Tuple[User, int]] = []
                # compile mask and test against each user
                for user_mask, user in user_masks.items():
                    for ban_id, ban_glob in ban_adds:
                        if ban_glob.match(user_mask):
                            affected.append((user, ban_id))

                if affected:
                    remove_op = await self._assure_op(channel)
                    # kick the bad guys
                    for user, ban_id in affected:
                        reason = ENFORCE_REASON.format(id=ban_id)
                        await self.send(build(
                            "KICK", [channel_name, user.nickname, reason]
                        ))
                    if remove_op:
                        await self.send(build(
                            "MODE", [channel_name, "-o", self.nickname]
                        ))

        elif (line.command == "PRIVMSG" and
                line.source is not None and
                line.params[1].startswith(CONFIG.trigger)):
            sender  = self.casefold(line.hostmask.nickname)
            message = line.params[1].replace(CONFIG.trigger, "", 1)
            command, _, message = message.partition(" ")
            command = command.lower()

            if command == "comment":
                ban_id_s, _, message = message.partition(" ")
                ban_id = -1
                if ban_id_s == "^" and self.is_channel(line.params[0]):
                    channel = self.casefold(line.params[0])
                    last_ban_id = DB.get_last(channel)
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
                await self.send(build("NOTICE", [sender, out]))

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
        config: Config):
    bot = Bot()
    await bot.add_server(params.host, params)

    global CONFIG
    CONFIG = config

    global DB
    DB = BanDatabase(config.db)

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

    # grab db filename and list of channels to join
    bot_config = Config(
        os.path.expanduser(config["db"]),
        [c.strip() for c in config["channels"].split(",")],
        config.get("trigger", "!"),
        config.get("chanserv", "no") == "yes",
        config.get("ban-enforce", "no") == "yes",
        config.get("quiet", None)
    )

    asyncio.run(main(params, bot_config))
