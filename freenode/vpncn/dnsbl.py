from typing import Optional

class DNSBL(object):
    hostname: str
    def __init__(self, hostname: Optional[str]=None):
        if hostname is not None:
            self.hostname = hostname

    def reason(self, result: str) -> str:
        return "unknown"

class ZenSpamhaus(DNSBL):
    hostname = "zen.spamhaus.org"
    def reason(self, result: str) -> str:
        result = result.rsplit(".", 1)[1]
        if result in ["2", "3", "9"]:
            return "spam"
        elif result in ["4", "5", "6", "7"]:
            return "exploits"
        else:
            return super().reason(result)

class EFNetRBL(DNSBL):
    hostname = "rbl.efnetrbl.org"
    def reason(self, result: str) -> str:
        result = result.rsplit(".", 1)[1]
        if result == "1":
            return "proxy"
        elif result in ["2", "3"]:
            return "spamtap"
        elif result == "4":
            return "tor"
        elif result == "5":
            return "flooding"
        else:
            return super().reason(result)

class DroneBL(DNSBL):
    hostname = "dnsbl.dronebl.org"
    def reason(self, result: str) -> str:
        result = result.rsplit(".", 1)[1]
        if result in ["8", "9", "10", "11", "14"]:
            return "proxy"
        elif result in ["3", "6", "7"]:
            return "flooding"
        elif result in ["12", "13", "15", "16"]:
            return "exploits"
        else:
            return super().reason(result)

class AbuseAtCBL(DNSBL):
    hostname = "cbl.abuseat.org"
    def reason(self, result: str) -> str:
        result = result.rsplit(".", 1)[1]
        if result == "2":
            return "abuse"
        else:
            return super().reason(result)

DNSBLS = [
    ZenSpamhaus(),
    EFNetRBL(),
    DroneBL(),
    AbuseAtCBL()
]
