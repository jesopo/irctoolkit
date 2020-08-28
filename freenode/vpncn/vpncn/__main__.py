import asyncio
from argparse import ArgumentParser
from .        import main

if __name__ == "__main__":
    parser = ArgumentParser(
        description="Catch VPN users by certificate fingerprinting")
    parser.add_argument("config")
    args = parser.parse_args()

    asyncio.run(main(args.config))
