import asyncio, re, ssl, traceback
from argparse     import ArgumentParser
from configparser import ConfigParser
from typing       import List, Tuple

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.backends import default_backend
from async_timeout import timeout as timeout_

from irctokens import build, Line
from ircrobots import Bot as BaseBot
from ircrobots import Server as BaseServer
from ircrobots import ConnectionParams, SASLUserPass

ACC:     bool = True
CHANS:   List[str] = []
BAD:     List[str] = []
ACTIONS: List[str] = []

PATTERNS: List[Tuple[str, str, str]] = [
    # match @[...]/ip.[...]
    (r"^.+/ip\.(?P<ip>[^/]+)#.*$", "*!*@*/ip.{IP}"),
    # match #https://webchat.freenode.net
    (r"^(?P<ip>[^/]+)#https://webchat.freenode.net$", "*!*@{IP}")
]

TLS = ssl.SSLContext(ssl.PROTOCOL_TLS)
TLS.options |= ssl.OP_NO_SSLv2
TLS.options |= ssl.OP_NO_SSLv3
TLS.load_default_certs()

async def _common_name(ip: str, port: int) -> str:
    reader, writer = await asyncio.open_connection(ip, port, ssl=TLS)
    der_cert = writer.transport._ssl_protocol._sslpipe.ssl_object.getpeercert(True)
    writer.close()
    await writer.wait_closed()

    pem_cert = ssl.DER_cert_to_PEM_cert(der_cert).encode("ascii")
    cert     = x509.load_pem_x509_certificate(pem_cert, default_backend())
    cns      = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    return cns[0].value

class Server(BaseServer):
    async def _act(self,
            line: Line,
            mask: str,
            ip:   str,
            cn:   str):
        data = {
            "CHAN": line.params[0],
            "NICK": line.hostmask.nickname,
            "MASK": mask,
            "IP":   ip,
            "CN":   cn
        }

        for action in ACTIONS:
            action_f = action.format(**data)
            await self.send_raw(action_f)

    async def line_read(self, line: Line):
        print(f"{self.name} < {line.format()}")
        if   line.command == "001":
            await self.send(build("JOIN", [",".join(CHANS)]))
        elif (line.command == "JOIN" and
                not self.is_me(line.hostmask.nickname)):
            user = self.users[self.casefold(line.hostmask.nickname)]
            if not ACC or not user.account:
                fingerprint = f"{line.hostmask.hostname}#{user.realname}"
                for pattern, mask in PATTERNS:
                    match = re.search(pattern, fingerprint)
                    if match:
                        ip     = match.group("ip")
                        mask_f = mask.format(IP=ip)

                        try:
                            async with timeout_(4):
                                common_name = await _common_name(ip, 443)
                        except TimeoutError:
                            print("timeout")
                        except Exception as e:
                            traceback.print_exc()
                        else:
                            if common_name in BAD:
                                await self._act(line, mask_f, ip, common_name)

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
        bad:       List[str],
        actions:   List[str]):
    global ACC, CHANS, BAD, ACTIONS
    ACC     = acc_grace
    CHANS   = chans
    BAD     = bad
    ACTIONS = actions

    bot = Bot()
    params = ConnectionParams(nickname, hostname, 6697, True)
    params.sasl = SASLUserPass(sasl_user, sasl_pass)

    await bot.add_server("server", params)
    await bot.run()

def _strip_list(lst: List[str]) -> List[str]:
    return list(filter(bool, [l.strip() for l in lst]))

if __name__ == "__main__":
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
    bad       = _strip_list(config["bot"]["bad"].split(","))
    actions   = _strip_list(config["bot"]["actions"].split(";"))

    asyncio.run(main(
        hostname,
        nickname,
        sasl_user,
        sasl_pass,
        acc_grace,
        chans,
        bad,
        actions
    ))
