"""
MAX — My Autonomous eXecutor
Entry point and CLI launcher.
"""

import asyncio
import argparse
import sys
import logging
from pathlib import Path

from config.settings import Settings
from agent import MAXAgent
from interfaces.cli_interface import CLIInterface
from interfaces.telegram_interface import TelegramInterface
from interfaces.discord_interface import DiscordInterface

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("MAX")

BANNER = r"""
  __  __     _     __  __
 |  \/  |   / \   \ \/ /
 | |\/| |  / _ \   >  <
 | |  | | / ___ \ / /\ \
 |_|  |_|/_/   \_/_/  \_\

 My Autonomous eXecutor — v0.1.0
 Your AI. Your hardware. Your rules.
"""


def parse_args():
    parser = argparse.ArgumentParser(description="MAX — My Autonomous eXecutor")
    parser.add_argument(
        "--interface",
        choices=["cli", "telegram", "discord"],
        default=None,
        help="Interface to use (overrides .env setting)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LLM model to use (overrides .env setting)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--no-banner",
        action="store_true",
        help="Suppress startup banner",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.no_banner:
        print(BANNER)

    # Load settings from .env
    settings = Settings()

    # CLI args override .env
    if args.interface:
        settings.interface = args.interface
    if args.model:
        settings.llm_model = args.model

    logger.info(f"Starting MAX with interface={settings.interface}, model={settings.llm_model}")

    # Initialize core agent
    agent = MAXAgent(settings=settings)
    await agent.initialize()

    # Select and launch interface
    interface_map = {
        "cli": CLIInterface,
        "telegram": TelegramInterface,
        "discord": DiscordInterface,
    }

    interface_cls = interface_map.get(settings.interface)
    if not interface_cls:
        logger.error(f"Unknown interface: {settings.interface}")
        sys.exit(1)

    interface = interface_cls(agent=agent, settings=settings)

    try:
        await interface.start()
    except KeyboardInterrupt:
        logger.info("Shutting down MAX...")
    finally:
        await agent.shutdown()
        logger.info("MAX offline. Goodbye.")


if __name__ == "__main__":
    asyncio.run(main())
