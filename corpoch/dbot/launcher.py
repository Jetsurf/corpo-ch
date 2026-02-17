#!/usr/bin/env python
import asyncio
import contextlib
import logging
import os
import sys

from .bot import CorpoDbot

def run_bot():
    loop = asyncio.get_event_loop()
    log = logging.getLogger()

    bot = CorpoDbot()
    bot.run()