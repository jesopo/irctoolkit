import os
from configparser import ConfigParser
from dataclasses  import dataclass
from enum         import IntEnum
from typing       import Any, Dict, List, Optional

@dataclass
class BotConfig(object):
    data:     str
    channels: List[str]
    trigger:  str
    chanserv: bool
    enforce:  bool
    quiet:    Optional[str]

def _yes_bool(s: str) -> bool:
    return s in ["yes", "on", "1"]
def _yes_str(b: bool) -> str:
    return "yes" if b else "no"
@dataclass
class ChannelConfig(object):
    trigger:  Optional[str]  = None
    chanserv: Optional[bool] = None
    enforce:  Optional[bool] = None

    def set(self, key: str, value: str) -> Any:
        if key   == "trigger":
            self.trigger  = value
            return self.trigger
        elif key == "chanserv":
            self.chanserv = _yes_bool(value)
            return self.chanserv
        elif key == "enforce":
            self.enforce  = _yes_bool(value)
            return self.enforce
        else:
            raise KeyError(key)
    def out(self) -> Dict[str, str]:
        d: Dict[str, str] = {}
        if self.trigger  is not None:
            d["trigger"]  = self.trigger
        if self.enforce  is not None:
            d["enforce"]  = _yes_str(self.enforce)
        if self.chanserv is not None:
            d["chanserv"] = _yes_str(self.chanserv)
        return d

class ChannelConfigs(object):
    def __init__(self, location: str):
        self._location = location
        self._channels: Dict[str, ChannelConfig] = {}
    def get(self, channel: str) -> ChannelConfig:
        if not channel in self._channels:
            self._channels[channel] = ChannelConfig()
        return self._channels[channel]

    def set(self, channel: str):
        existing = self.get(channel)

        if existing:
            if not os.path.isdir(self._location):
                os.mkdir(self._location)
            filename   = os.path.join(self._location, f"{channel}.conf")
            config_obj = ConfigParser()
            config_obj.read_dict({"bot": existing.out()})
            with open(filename, "w") as file_obj:
                config_obj.write(file_obj)

class Types(IntEnum):
    BAN   = 1
    QUIET = 2
