# vpncn

A bot to scan users for commonly abused VPN providers, via tls certificate
finterprinting.

## requirements

```
$ pip3 install -r requirements.txt
```

## running the bot
copy `vpncn.conf.example` to `vpncn.conf`, edit the relevant values, and:
```
$ python3 vpncn vpncn.conf
```
