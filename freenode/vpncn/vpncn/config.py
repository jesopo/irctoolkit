import yaml, re
from dataclasses import dataclass
from typing      import Dict, List, Optional, Pattern, Tuple

from ircrobots.glob import Glob, compile as glob_compile

@dataclass
class CertPattern(object):
    name: str
    find: List[Pattern]

@dataclass
class Config(object):
    hostname:      str
    nickname:      str
    sasl:          Tuple[str, str]
    admins:        List[Glob]
    host_patterns: List[Tuple[Pattern, str]]
    act_sets:      Dict[str, List[Tuple[bool, str]]]
    act_defaults:  List[str]
    channels:      Dict[str, Optional[List[str]]]
    bad:           Dict[int, List[CertPattern]]

def load_config(path: str) -> Config:
    with open(path) as f:
        config = yaml.safe_load(f.read())

    host_patterns: List[Tuple[Pattern, str]] = []
    for key, value in config["host-patterns"]:
        host_patterns.append((re.compile(key, re.I), value))

    chans: Dict[str, Optional[List[str]]] = {}
    for chan in config["channels"]:
        if isinstance(chan, str):
            chans[chan]   = None
        elif isinstance(chan, dict):
            chan_k = list(chan.keys())[0]
            chans[chan_k] = chan[chan_k]

    cert_patterns: Dict[str, CertPattern] = {}
    for cert_name, cert_values in config["cert-patterns"].items():
        name = cert_values["name"]
        find = cert_values["find"]
        if (isinstance(name, str) and
                isinstance(find, list)):
            comp = [re.compile(f, re.I) for f in find]
            cert_patterns[cert_name] = CertPattern(name, comp)

    bad: Dict[int, List[CertPattern]] = {}
    for port, cert_names in config["bad"].items():
        bad[port] = [cert_patterns[n] for n in cert_names]

    return Config(
        config["hostname"],
        config["nickname"],
        (config["sasl"]["username"], config["sasl"]["password"]),
        [glob_compile(m) for m in config["admins"]],
        host_patterns,
        config["act-sets"],
        config["act-default"],
        chans,
        bad
    )
