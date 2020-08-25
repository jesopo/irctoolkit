import asyncio, itertools, re, ssl, traceback
from argparse     import ArgumentParser
from configparser import ConfigParser
from dataclasses  import dataclass
from typing       import Awaitable, Dict, List, Optional, Pattern, Set, Tuple

import yaml
from OpenSSL import crypto

from async_timeout  import timeout as timeout_

from irctokens import build, Line, tokenise
from ircstates import Channel
from ircrobots import Bot as BaseBot
from ircrobots import Server as BaseServer
from ircrobots import ConnectionParams, SASLUserPass
from ircrobots.glob     import compile as glob_compile, Glob
from ircstates.numerics import *
from ircrobots.matching import ANY, Folded, Nick, Response, SELF

@dataclass
class Config(object):
    hostname: str
    nickname: str
    sasl:     Tuple[str, str]
    admins:   List[Glob]
    patterns: Dict[Pattern, str]
    act_sets: Dict[str, List[Tuple[bool, str]]]
    channels: Dict[str, List[str]]
    bad:      Dict[int, Dict[Pattern, str]]
CONFIG: Config

TLS = ssl.SSLContext(ssl.PROTOCOL_TLS)

def _bytes_dict(d: List[Tuple[bytes, bytes]]) -> Dict[str, str]:
    return {k.decode("utf8"): v.decode("utf8") for k, v in d}

async def _cert_values(
        ip:   str,
        port: int
        ) -> List[Tuple[str, str]]:
    reader, writer = await asyncio.open_connection(ip, port, ssl=TLS)
    cert = writer.transport._ssl_protocol._sslpipe.ssl_object.getpeercert(True)
    writer.close()
    await writer.wait_closed()

    x509 = crypto.load_certificate(crypto.FILETYPE_ASN1, cert)

    subject = _bytes_dict(x509.get_subject().get_components())
    issuer  = _bytes_dict(x509.get_issuer().get_components())

    values: List[Tuple[str, str]] = [
        ("scn", subject['CN']),
        ("icn", issuer['CN']),
    ]
    if "O" in subject:
        values.append(("son", subject["O"]))
    if "O" in issuer:
        values.append(("ion", issuer["O"]))

    for i in range(x509.get_extension_count()):
        ext = x509.get_extension(i)
        if ext.get_short_name() == b"subjectAltName":
            sans = str(ext).split(", ")
            sans = [s.split(":", 1)[1] for s in sans]
            for san in sans:
                values.append(("san", san))

    return values

async def _cert_match(
        ip:   str,
        port: int
        ) -> Optional[Tuple[int, Pattern]]:

    try:
        async with timeout_(4):
            values_t = await _cert_values(ip, port)
    except asyncio.TimeoutError:
        print("timeout")
    except (ConnectionRefusedError,
            ConnectionResetError):
        pass
    except Exception as e:
        traceback.print_exc()
    else:
        values = [f"{k}:{v}" for k, v in values_t]
        for pattern in CONFIG.bad[port].keys():
            for value in values:
                if pattern.fullmatch(value):
                    return (port, pattern)
    return None

async def _cert_matches(
        ip:    str,
        ) -> Optional[str]:

    coros = [_cert_match(ip, port) for port in CONFIG.bad.keys()]
    tasks = set(asyncio.ensure_future(c) for c in coros)
    while tasks:
        finished, unfinished = await asyncio.wait(
            tasks, return_when=asyncio.FIRST_COMPLETED
        )
        for fin in finished:
            result = fin.result()
            if result is not None:
                for task in unfinished:
                    task.cancel()
                if unfinished:
                    await asyncio.wait(unfinished)
                port, pattern = result
                description   = CONFIG.bad[port][pattern]

                return f"{pattern.pattern} (:{port} {description})"
        tasks = set(asyncio.ensure_future(f) for f in unfinished)
    return None

async def _match(ip: str) -> Optional[str]:
    reason = await _cert_matches(ip)
    return reason

CHANSERV = Nick("ChanServ")

class Server(BaseServer):
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
            line:   Line,
            mask:   str,
            ip:     str,
            reason: str):
        chan     = self.channels[self.casefold(line.params[0])]
        act_sets = CONFIG.channels.get(chan.name_lower, [])
        act_cmds = [CONFIG.act_sets[a] for a in act_sets]
        acts     = list(itertools.chain(*act_cmds))
        # put False (non-op) acts first
        acts.sort(key=lambda x: x[0])

        data = {
            "CHAN":   chan.name,
            "NICK":   line.hostmask.nickname,
            "USER":   line.hostmask.username,
            "HOST":   line.hostmask.hostname,
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

    async def line_read(self, line: Line):
        print(f"{self.name} < {line.format()}")
        if   line.command == "001":
            chans = list(CONFIG.channels.keys())
            await self.send(build("JOIN", [",".join(chans)]))
        elif (line.command == "JOIN" and
                not self.is_me(line.hostmask.nickname)):
            nick = line.hostmask.nickname
            await self.send(build("WHO", [nick, "%int,111"]))
            who_line = await self.wait_for(
                Response(RPL_WHOSPCRPL, [ANY, "111", ANY, Folded(nick)])
            )
            host = who_line.params[2]
            if (host == "255.255.255.255" and
                    line.hostmask.hostname is not None):
                host = line.hostmask.hostname

            user = self.users[self.casefold(nick)]
            fingerprint = f"{host}#{user.realname}"
            for pattern, mask_templ in CONFIG.patterns.items():
                match = pattern.search(fingerprint)
                if match:
                    chan = self.channels[self.casefold(line.params[0])]
                    ip   = match.group("ip")
                    mask = mask_templ.format(IP=ip)

                    list_modes = (chan.list_modes.get("b", [])+
                        chan.list_modes.get("q", []))
                    if not mask in list_modes:
                        reason = await _match(ip)
                        if reason is not None:
                            await self._act(line, mask, ip, reason)
                    else:
                        print("already caught")

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

    async def line_send(self, line: Line):
        print(f"{self.name} > {line.format()}")

class Bot(BaseBot):
    def create_server(self, name: str):
        return Server(self, name)

async def main(config: Config):
    global CONFIG
    CONFIG = config

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

def init():
    parser = ArgumentParser(
        description="Catch VPN users by certificate fingerprinting")
    parser.add_argument("config")
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f.read())

    patterns: Dict[Pattern, str] = {}
    for key, value in config["patterns"].items():
        patterns[re.compile(key)] = value

    act_default = config["act-default"]
    chans: Dict[str, List[str]] = {}
    for chan in config["channels"]:
        if isinstance(chan, str):
            chans[chan]   = act_default
        elif isinstance(chan, dict):
            chan_k = list(chan.keys())[0]
            chans[chan_k] = chan[chan_k]

    bad_c = config["bad"]
    bad: Dict[int, Dict[Pattern, str]] = {}
    for port in bad_c:
        if (isinstance(port, int) and
                isinstance(bad_c[port], dict)):
            bad[port] = {}
            for key, value in bad_c[port].items():
                bad[port][re.compile(key)] = value

    config = Config(
        config["hostname"],
        config["nickname"],
        (config["sasl"]["username"], config["sasl"]["password"]),
        [glob_compile(m) for m in config["admins"]],
        patterns,
        config["act-sets"],
        chans,
        bad
    )

    asyncio.run(main(config))
