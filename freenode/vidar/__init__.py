import asyncio, os
from typing import cast, Dict, List, Optional, Set

from irctokens import build, Line
from ircstates import User
from ircstates.names import Name
from ircrobots import Bot as BaseBot
from ircrobots import Server as BaseServer
from ircrobots import ConnectionParams, SASLUserPass

from ircstates.numerics import *
from ircrobots.matching import Response, Responses, Folded, Nick, SELF
from ircrobots.glob     import Glob, collapse as gcollapse, compile as gcompile

from .database import MaskDatabase

TRIGGER = "!"

ADMINS_S = [
    "*!*@bitbot/jess"
]
ADMINS = [gcompile(m) for m in ADMINS_S]

def _masks(user: User) -> List[str]:
    masks: List[str] = []

    if (user.username is not None and
            user.hostname is not None and
            user.realname is not None):
        nickuser = f"{user.nickname}!{user.username}"
        hostmask = f"{nickuser}@{user.hostname}"
        masks.append(f"$m:{hostmask}")
        masks.append(f"$x:{hostmask}#{user.realname}")
        masks.append(f"$r:{user.realname}")

        if user.ip is not None and not user.ip == user.hostname:
            ipmask = f"{nickuser}@{user.ip}"
            masks.append(f"$m:{ipmask}")
            masks.append(f"$x:{ipmask}#{user.realname}")
        elif "/ip." in user.hostname:
            _, ip = user.hostname.rsplit("/ip.")
            ipmask = f"{nickuser}@{ip}"
            masks.append(f"$m:{ipmask}")
            masks.append(f"$x:{ipmask}#{user.realname}")


    if user.account is not None:
        masks.append(f"$a:{user.account}")
        masks.append("$a")
    else:
        masks.append("$~a")

    return masks

def _is_admin(hostmask: str) -> bool:
    for mask in ADMINS:
        if mask.match(hostmask):
            return True
    else:
        return False

class VidarUser(User):
    def __init__(self, name: Name):
        super().__init__(name)
        self.caught: Set[int] = set()

class Server(BaseServer):
    def __init__(self,
            bot:  BaseBot,
            name: str,
            database:   MaskDatabase,
            log_chan:   str,
            watch_chan: str):
        super().__init__(bot, name)

        self._database   = database
        self._log_chan   = log_chan
        self._watch_chan = watch_chan

        self._new_users: Set[str] = set()

        self._watch_masks: Dict[int, Glob] = {}
        for mask_id, mask in self._database.get_all():
            self._watch_masks[mask_id] = gcompile(mask)

    def create_user(self, nickname: Name) -> VidarUser:
        return VidarUser(nickname)

    def line_preread(self, line: Line):
        print(f"{self.name} < {line.format()}")
    def line_presend(self, line: Line):
        print(f"{self.name} > {line.format()}")

    async def _check_user(self, user: User, cause: str):
        muser = cast(VidarUser, user)
        masks = _masks(user)
        for mask_id, watch_glob in self._watch_masks.items():
            watch_mask    = self._database.get(mask_id)
            watch_comment = self._database.get_comment(mask_id)
            if mask_id in muser.caught:
                continue

            for mask in masks:
                if watch_glob.match(mask):
                    out = (f"[{cause}] "
                        f"mask match ({watch_mask}) "
                        f"for {user.hostmask()}")
                    if watch_comment is not None:
                        out += f": {watch_comment}"
                    await self._log(out)

                    muser.caught.add(mask_id)
                    break

    async def line_read(self, line: Line):
        if line.command == "001":
            await self.send(build(
                "JOIN", [f"{self._log_chan},{self._watch_chan}"]
            ))

        elif (line.command == "JOIN" and
                line.source is not None and
                self.casefold(line.params[0]) == self._watch_chan):
            folded = self.casefold(line.hostmask.nickname)
            if not folded == self.nickname_lower:
                self._new_users.add(folded)
                await self.send(self.prepare_whox(line.hostmask.nickname))

        elif line.command == RPL_WHOSPCRPL:
            folded = self.casefold(line.params[6])
            if folded in self._new_users:
                self._new_users.remove(folded)
                if folded in self.users:
                    user  = self.users[folded]
                    await self._check_user(user, "JOINX")

        elif line.command in ["ACCOUNT", "CHGHOST", "NICK"]:
            folded = self.casefold(line.hostmask.nickname)
            if (not folded == self.nickname_lower and
                    folded in self.users):
                user = self.users[folded]
                if self._watch_chan in user.channels:
                    await self._check_user(user, line.command)

        elif (line.command == "PRIVMSG" and
                line.source is not None):
            folded  = self.casefold(line.params[0])
            message = line.params[1]
            if (folded in [self._log_chan, self.nickname_lower] and
                    message.startswith(TRIGGER) and
                    _is_admin(line.source)):

                reply_target = self._log_chan
                reply_method = "PRIVMSG"
                if self.is_me(folded):
                    reply_target = line.hostmask.nickname
                    reply_method = "NOTICE"

                argv    = message.split(" ")
                command = argv.pop(0).replace(TRIGGER, "", 1)
                argc    = len(argv)

                if command == "mask" and len(argv) > 1:

                    subcommand  = argv[0]
                    raw_mask    = gcollapse(argv[1])
                    mask        = raw_mask

                    if not mask.startswith("$"):
                        mask = f"$m:{mask}"
                    ext, sep, mask = mask.partition(":")
                    mask = ext + sep + self.casefold(mask)

                    comment: Optional[str] = None
                    if argc > 2:
                        comment = " ".join(argv[2:])

                    existing = self._database.find(mask)

                    if subcommand == "add":
                        if existing is None:
                            mask_id = self._database.add(mask, comment)
                            self._watch_masks[mask_id] = gcompile(mask)

                            out = f"now watching {mask} ({mask_id})"
                            await self.send(build(
                                reply_method, [reply_target, out]
                            ))
                        else:
                            print("it exists!!!")
                            # error message
                            pass
                    elif subcommand == "remove":
                        if existing is not None:
                            self._database.remove(existing)
                            del self._watch_masks[existing]

                            out = f"no longer watching {mask}"
                            await self.send(build(
                                reply_method, [reply_target, out]
                            ))
                        else:
                            # error message
                            print("it does not exist!!")
                    elif subcommand == "comment":
                        if existing is not None:
                            existing_mask = self._database.get(mask_id)
                            self._database.set_comment(existing, comment)

                            if comment is not None:
                                out = f"set comment for {existing_mask}"
                            else:
                                out = f"removed comment for {existing_mask}"
                        else:
                            print("it does not exist!!")

    async def _log(self, line: str):
        await self.send(build("PRIVMSG", [self._log_chan, line]))

class Bot(BaseBot):
    def __init__(self,
            database:   str,
            log_chan:   str,
            watch_chan: str):
        super().__init__()
        self._database   = MaskDatabase(database)
        self._log_chan   = log_chan
        self._watch_chan = watch_chan

    def create_server(self, name: str):
        return Server(self,
            name,
            self._database,
            self._log_chan,
            self._watch_chan)

async def main(
        database:   str,
        nickname:   str,
        sasl:       Optional[str],
        log_chan:   str,
        watch_chan: str):

    db_dir = os.path.dirname(os.path.abspath(database))
    if not os.path.isdir(db_dir):
        os.makedirs(db_dir)

    bot = Bot(database, log_chan, watch_chan)
    params = ConnectionParams(
        nickname,
        "chat.freenode.net",
        6697,
        True)

    if sasl:
        account, _, password = sasl.partition(":")
        params.sasl = SASLUserPass(account, password)

    await bot.add_server("freenode", params)
    await bot.run()
