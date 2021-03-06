import os
import asyncio
import discord
import emoji
import mysql
from discord.ext import commands

from ags_experiments.settings import guild_settings
from ags_experiments import set_activity
from ags_experiments.client_tools import ClientTools
from ags_experiments.database import cnx, cursor
from ags_experiments.database.database_tools import DatabaseTools, insert_users, insert_settings, insert_role, \
    update_role
from ags_experiments.role_c import DbRole
from ags_experiments.settings.config import config, strings
from ags_experiments.logger import logger

if config['discord']['debug'] or bool(os.environ.get('discord_experiments_debug')):
    logger.info("Running in debug mode.")
    debug = True
    prefix = config['discord']['prefix_debug']
else:
    logger.info("Running in production mode.")
    debug = False
    prefix = config['discord']['prefix']

shard_count = config['discord'].get("shard_count")
if shard_count is None:
    logger.warn(
        "config['discord']['shard_count'] is not set - defaulting to 1 shard")
    shard_count = 1

client = commands.AutoShardedBot(
    command_prefix=prefix, owner_id=config['discord']['owner_id'], shard_count=shard_count)

client_tools = ClientTools(client)
database_tools = DatabaseTools(client)
token = config['discord']['token']


@client.event
async def on_ready():
    game = discord.Game("Starting")
    await client.change_presence(activity=game)
    logger.info("Connected to Discord as {} ({})".format(
        client.user.name, client.user.id))
    
    # This needs to be here, so that all the other cogs can be loaded
    client.load_extension("ags_experiments.cogs.loader")
    await set_activity(client)

    for guild in client.guilds:
            guild_settings.add_guild(guild)
    members = []
    if not bool(config['discord'].get("skip_scrape")):
        for guild in client.guilds:
            if debug:
                    logger.info(
                        "Found guild {} - {} channels".format(guild.name, len(guild.text_channels)))
            for member in guild.members:
                name = database_tools.opted_in(user_id=member.id)
                if name is not False:
                    if name not in members:
                        members.append(member)
            logger.info(
                "Initialising building data profiles on existing messages. This will take a while.")
    await client_tools.build_data_profile(members, limit=None)
    

@client.event
async def on_message(message):
    await set_activity(client)
    return await client.process_commands(message)


@client.event
async def on_command_error(ctx, error):
    if not debug:
        if isinstance(error, commands.CommandInvokeError):
            await client_tools.error_embed(ctx, error)
        else:
            if isinstance(error, commands.NoPrivateMessage):
                embed = discord.Embed(description="")
            elif isinstance(error, commands.DisabledCommand):
                embed = discord.Embed(
                    description=strings['errors']['disabled'])
            elif isinstance(error, commands.MissingRequiredArgument):
                embed = discord.Embed(
                    description=strings['errors']['argument_missing'].format(error.args[0]))
            elif isinstance(error, commands.BadArgument):
                embed = discord.Embed(
                    description=strings['errors']['bad_argument'].format(error.args[0]))
            elif isinstance(error, commands.TooManyArguments):
                embed = discord.Embed(
                    description=strings['errors']['too_many_arguments'])
            elif isinstance(error, commands.BotMissingPermissions):
                embed = discord.Embed(description="{}".format(
                    error.args[0].replace("Bot", strings['bot_name'])))
            elif isinstance(error, commands.MissingPermissions):
                embed = discord.Embed(description="{}".format(error.args[0]))
            elif isinstance(error, commands.NotOwner):
                embed = discord.Embed(
                    description=strings['errors']['not_owner'].format(strings['owner_firstname']))
            elif isinstance(error, commands.CheckFailure):
                embed = discord.Embed(
                    description=strings['errors']['no_permission'])
            elif isinstance(error, commands.CommandError):
                if not config['discord']['prompt_command_exist']:
                    embed = discord.Embed(description="")
                    return
                embed = discord.Embed(
                    description=strings['errors']['command_not_found'])
            else:
                embed = discord.Embed(
                    description=strings['errors']['placeholder'].format(strings['bot_name']))
            if embed:
                embed.colour = 0x4c0000
                await ctx.send(embed=embed, delete_after=config['discord']['delete_timeout'])
    raise error


@client.event
async def on_member_join(member):
    database_tools.add_user(member) # handles adding the user to our database


@client.event
async def on_guild_join(guild):
    guild_settings.add_guild(guild=guild)


if __name__ == "__main__":
    client.run(token)
