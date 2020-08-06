import asyncio, re, ssl, traceback
from argparse     import ArgumentParser
from configparser import ConfigParser
from typing       import Dict, List, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.backends import default_backend

from async_timeout  import timeout as timeout_
from aiodnsresolver import DnsRecordDoesNotExist, Resolver, TYPES

from irctokens import build, Line
from ircrobots import Bot as BaseBot
from ircrobots import Server as BaseServer
from ircrobots import ConnectionParams, SASLUserPass
from ircrobots.glob import compile as glob_compile, Glob

from .dnsbl import DNSBLS

ACC:      bool = True
CHANS:    List[str] = []
BAD:      Dict[str, str] = {}
ACT_SOFT: List[str] = []
ACT_HARD: List[str] = []
ADMINS:   List[Glob] = []

PATTERNS: List[Tuple[str, str]] = [
    # match @[...]/ip.[...]
    (r"^.+/ip\.(?P<ip>[^/]+)#.*$", "*!*@*/ip.{IP}"),
    # match #https://webchat.freenode.net
    (r"^(?P<ip>[^/]+)#https://webchat.freenode.net$", "*!*@{IP}")
]

TLS = ssl.SSLContext(ssl.PROTOCOL_TLS)
TLS.options |= ssl.OP_NO_SSLv2
TLS.options |= ssl.OP_NO_SSLv3
TLS.load_default_certs()

async def _cert_values(ip: str, port: int) -> Dict[str, str]:
    reader, writer = await asyncio.open_connection(ip, port, ssl=TLS)
    der_cert = writer.transport._ssl_protocol._sslpipe.ssl_object.getpeercert(True)
    writer.close()
    await writer.wait_closed()

    pem_cert = ssl.DER_cert_to_PEM_cert(der_cert).encode("ascii")
    cert     = x509.load_pem_x509_certificate(pem_cert, default_backend())

    values: Dict[str, str] = {}
    cns = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
    if cns:
        values["cn"] = cns[0].value
    ons = cert.subject.get_attributes_for_oid(x509.oid.NameOID.ORGANIZATION_NAME)
    if ons:
        values["on"] = ons[0].value
    return values

async def _cert_match(ip: str) -> Optional[str]:
    try:
        async with timeout_(4):
            values = await _cert_values(ip, 443)
    except TimeoutError:
        print("timeout")
    except Exception as e:
        traceback.print_exc()
    else:
        for key, value in values.items():
            kv = f"{key}:{value}".lower().strip()
            if kv in BAD:
                return kv
    return None

async def _dnsbl_match(ip: str) -> Optional[str]:
    ip_rev = ".".join(reversed(ip.split(".")))
    resolver, _ = Resolver()

    for dnsbl in DNSBLS:
        domain = f"{ip_rev}.{dnsbl.hostname}"
        try:
            results = await resolver(domain, TYPES.A)
        except DnsRecordDoesNotExist:
            pass
        else:
            for result in results:
                reason = dnsbl.reason(result.exploded)
                return f"dnsbl:{dnsbl.hostname}:{reason}"
    return None

async def _match(ip: str) -> Optional[str]:
    reason =           await _cert_match(ip)
    reason = reason or await _dnsbl_match(ip)

    return reason

class Server(BaseServer):
    async def _act(self,
            acts:   List[str],
            line:   Line,
            mask:   str,
            ip:     str,
            reason: str):
        data = {
            "CHAN":   line.params[0],
            "NICK":   line.hostmask.nickname,
            "MASK":   mask,
            "IP":     ip,
            "REASON": reason
        }

        for action in acts:
            action_f = action.format(**data)
            await self.send_raw(action_f)

    async def line_read(self, line: Line):
        print(f"{self.name} < {line.format()}")
        if   line.command == "001":
            await self.send(build("JOIN", [",".join(CHANS)]))
        elif (line.command == "JOIN" and
                not self.is_me(line.hostmask.nickname)):
            user = self.users[self.casefold(line.hostmask.nickname)]
            fingerprint = f"{line.hostmask.hostname}#{user.realname}"
            for pattern, mask in PATTERNS:
                match = re.search(pattern, fingerprint)
                if match:
                    ip     = match.group("ip")
                    mask_f = mask.format(IP=ip)

                    reason = await _match(ip)
                    if reason is not None:
                        await self._act(ACT_SOFT, line, mask_f, ip, reason)
                        if not ACC or not user.account:
                            await self._act(ACT_HARD, line, mask_f, ip, reason)
        elif (line.command == "INVITE" and
                self.is_me(line.params[0])):
            userhost = f"{line.hostmask.username}@{line.hostmask.hostname}"
            for admin_mask in ADMINS:
                if admin_mask.match(userhost):
                    await self.send(build("JOIN", [line.params[1]]))
                    break

    async def line_send(self, line: Line):
        print(f"{self.name} > {line.format()}")

class Bot(BaseBot):
    def create_server(self, name: str):
        return Server(self, name)

async def main(
        hostname:  str,
        nickname:  str,
        sasl_user: str,
        sasl_pass: str,
        acc_grace: bool,
        chans:     List[str],
        admins:    List[str],
        bad:       List[str],
        act_soft:  List[str],
        act_hard:  List[str]):
    global ACC, CHANS, BAD, ACT_SOFT, ACT_HARD
    ACC      = acc_grace
    CHANS    = chans
    ADMINS   = [glob_compile(a) for a in admins]
    ACT_SOFT = act_soft
    ACT_HARD = act_hard

    for bad_item in bad:
        BAD[bad_item.lower()] = bad_item

    bot = Bot()
    params = ConnectionParams(nickname, hostname, 6697, True)
    params.sasl = SASLUserPass(sasl_user, sasl_pass)

    await bot.add_server("server", params)
    await bot.run()

def _strip_list(lst: List[str]) -> List[str]:
    return list(filter(bool, [l.strip() for l in lst]))

def init():
    parser = ArgumentParser(
        description="Catch VPN users by :443 TLS certificate common-name")
    parser.add_argument("config")
    args = parser.parse_args()

    config = ConfigParser()
    config.read(args.config)

    hostname  = config["bot"]["hostname"]
    nickname  = config["bot"]["nickname"]
    sasl_user = config["bot"]["sasl-username"]
    sasl_pass = config["bot"]["sasl-password"]
    acc_grace = config["bot"]["account-grace"] == "on"
    chans     = _strip_list(config["bot"]["chans"].split(","))
    admins    = _strip_list(config["bot"]["admins"].split(","))
    bad       = _strip_list(config["bot"]["bad"].split(","))
    act_soft  = _strip_list(config["bot"]["act-soft"].split(";"))
    act_hard  = _strip_list(config["bot"]["act-hard"].split(";"))

    asyncio.run(main(
        hostname,
        nickname,
        sasl_user,
        sasl_pass,
        acc_grace,
        chans,
        admins,
        bad,
        act_soft,
        act_hard
    ))
