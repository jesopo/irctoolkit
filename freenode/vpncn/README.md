# vpncn

A bot to connect to certain users on port :443 and check their TLS
certificate's Common Name for bad VPN providers.

## requirements

> $ pip3 install ircrobots=0.2.12 cryptography==2.7

## running the bot
copy `vpncn.conf.example` to `vpncn.conf`, edit the relevant values, and:
> $ python3 vpncn.py vpncn.conf
