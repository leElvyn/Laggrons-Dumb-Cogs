import discord
import logging
import asyncio

from redbot.core.i18n import Translator, cog_i18n

log = logging.getLogger("red.laggron.tournaments")
_ = Translator("Tournaments", __file__)


class Templates():
    def __init__(self, bot, data):
        self.data = data