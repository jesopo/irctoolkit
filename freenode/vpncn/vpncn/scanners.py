import asyncio, ssl, traceback
from typing import Dict, List, Optional, Tuple

from async_timeout import timeout as timeout_
from OpenSSL       import crypto

from .config       import CertPattern

CERT_KEYS = [
    ("CN", "cn"),
    ("O",  "on")
]

TLS = ssl.SSLContext(ssl.PROTOCOL_TLS)

def _bytes_dict(d: List[Tuple[bytes, bytes]]) -> Dict[str, str]:
    return {k.decode("utf8"): v.decode("utf8") for k, v in d}

class CertScanner(object):
    def __init__(self, timeout: int = 5):
        self._timeout = timeout

    async def _values(self,
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

        values: List[Tuple[str, str]] = []
        for cert_key, match_key in CERT_KEYS:
            if cert_key in subject:
                values.append((f"s{match_key}", subject[cert_key]))
            if cert_key in issuer:
                values.append((f"i{match_key}", issuer[cert_key]))

        for i in range(x509.get_extension_count()):
            ext = x509.get_extension(i)
            if ext.get_short_name() == b"subjectAltName":
                sans = ext.get_data()[4:].split(b"\x82\x18")
                for san in sans:
                    values.append(("san", san.decode("latin-1")))

        return values


    async def _match(self,
            ip:    str,
            port:  int,
            certs: List[CertPattern]
            ) -> Optional[str]:

        try:
            async with timeout_(self._timeout):
                values_t = await self._values(ip, port)
        except (asyncio.TimeoutError,
                ConnectionError):
            pass
        except Exception as e:
            traceback.print_exc()
        else:
            values = [f"{k}:{v}" for k, v in values_t]
            for cert in certs:
                for pattern in cert.find:
                    for value in values:
                        if pattern.fullmatch(value):
                            return f"{value} (:{port} {cert.name})"
        return None

    async def scan(self,
            ip:  str,
            bad: Dict[int, List[CertPattern]]
            ) -> Optional[str]:
        coros = [self._match(ip, p, c) for p, c in bad.items()]
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

                    return result
            tasks = set(asyncio.ensure_future(f) for f in unfinished)
        return None

