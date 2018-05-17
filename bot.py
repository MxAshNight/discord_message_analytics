import datetime
import discord
import json
import markovify
import math
import mysql.connector
import re
import time
import sys


config_f = open("config.json")
config = json.load(config_f)

strings_f = open("strings.json")
strings = json.load(strings_f)[config['language']]

from discord.ext import commands

cnx_summer = mysql.connector.connect(**config['mysql'])
cursor_summer = cnx_summer.cursor()
cursor = cnx_summer.cursor()
token = config['discord']['token']
client = commands.Bot(command_prefix=config['discord']['prefix'])

disabled_groups = config['discord']['disabled_groups']

add_message = ("INSERT INTO messages (id, channel, time) VALUES (%s, %s, %s)")

add_message_summer = (
    "INSERT INTO summer_overlord_ai (id, channel, time, contents) VALUES (%s, %s, %s, %s)")


add_message_naomi = (
    "INSERT INTO naomi_ai (id, channel, time, contents) VALUES (%s, %s, %s, %s)")

add_message_custom = "INSERT INTO `%s` (id, channel_id, time, contents) VALUES (%s, %s, %s, %s)"

opt_in_message = """
We want to protect your information, and therefore you need to read the following in detail. We keep it brief as a lot of this is important for you to know incase you change your mind in the future.
			```
By proceeding with using this command, you agree for us to permanently store your data outside of Discord on a server located within Europe. This data will be used for data analysis and research purposes. Due to the worldwide nature of our team it may be transferred back out of the EU.

As per the GDPR, if you are under 18, please do not run this command, as data collection from minors is a big legal issue we don't want to get into. Sorry!

You also have the legal right to request your data is deleted at any point, which can be done by messaging Val. Upon deletion, it will be removed from all datasets, however communication regarding the datasets before your data removal may remain in this server, including in moderators private chats. You also have the legal right to request a full copy of all data stored on you at any point - this can also be done by messaging Val (and she'll be super happy to as it means she gets to show off her nerdy knowhow).

Your data may also be stored on data centres around the world, due to our usage of Google Team Drive to share files. All exports of the data will also be deleted by all moderators, including exports stored on data centres used for backups as discussed.```
"""


def is_owner():
    def predicate(ctx):
        if ctx.author.id == config['discord']['owner_id']:
            return True
        return False
    return commands.check(predicate)


@client.event
async def on_ready():

    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print("Has nitro: " + str(client.user.premium))
    print('------')

    print()

    print("Ensuring no data was lost during downtime. This may take a while if a lot of users are part of your experiments")

    for server in client.guilds:
        for member in server.members:
            name = opted_in(id=member.id)
            if name is not False:
                await build_data_profile(name, member, server)


@client.event
async def on_message(message):
    channel = message.channel
    user_exp = opted_in(id=message.author.id)

    if user_exp is not False:
        is_allowed = channel_allowed(
            channel.id, message.channel, message.channel.is_nsfw())
        if is_allowed:
            try:
                cursor_summer.execute(add_message_custom, (user_exp, int(message.id), str(message.channel.id), message.created_at.strftime('%Y-%m-%d %H:%M:%S'), message.content,))
            except mysql.connector.errors.IntegrityError:
                pass

    try:
        cursor_summer.execute(add_message, (int(message.id), str(message.channel.id), message.created_at.strftime('%Y-%m-%d %H:%M:%S')))
        cnx_summer.commit()
    except mysql.connector.errors.IntegrityError:
        pass

    return await client.process_commands(message)


@is_owner()
@client.command()
async def process_server(ctx):
    print("Logging")
    for channel in ctx.guild.text_channels:
        print(str(channel.name) + " is being processed. Please wait.")
        async for message in channel.history(limit=None, reverse=True):
            try:
                cursor.execute(add_message, (int(message.id), str(ctx.channel.id), message.created_at.strftime('%Y-%m-%d %H:%M:%S')))
            except mysql.connector.errors.DataError:
                print("Couldn't insert, probs a time issue")
            except mysql.connector.errors.IntegrityError:
                pass
        cnx_summer.commit()
        print(str(channel.name) + " has been processed.")
    print("Done!")
    return await client.process_commands(message)


@client.command()
async def experiments(ctx):
    message = ctx.message
    channel = message.channel

    author = message.author
    create_user = "INSERT INTO `users` (`user_id`, `username`) VALUES (%s, %s);"
    try:
        cursor_summer.execute(create_user, (author.id, author.name))
        cnx_summer.commit()

        em = discord.Embed(
            title=strings['data_collection']['opt_in_title'], description=opt_in_message)

        em.set_footer(text=strings['data_collection']['opt_in_footer'])
        return await channel.send(embed=em)
    except mysql.connector.errors.IntegrityError:
        get_user = "SELECT `username` FROM `users` WHERE  `user_id`=%s;"
        cursor_summer.execute(get_user, (author.id, ))
        username = (cursor_summer.fetchall()[0])[0]

        opt_in_user = "UPDATE `users` SET `opted_in`=b'1' WHERE  `user_id`=%s;"

        cursor_summer.execute(opt_in_user, (author.id, ))
        create_table = """
CREATE TABLE `%s` (
  `id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `channel_id` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `time` timestamp NULL DEFAULT NULL,
  `contents` longtext COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
		"""

        try:
            cursor_summer.execute(create_table, (username, ))
            await channel.send(strings['data_collection']['created_record'].format(username))
        except mysql.connector.errors.ProgrammingError:
            await channel.send(strings['data_collection']['update_record'].format(username))

    name = opted_in(id=message.author.id)

    await channel.send(strings['data_collection']['data_track_start'])
    await build_data_profile(name, author, message.guild)
    await channel.send(strings['data_collection']['complete'].format(author.name))


@is_owner()
@client.command()
async def is_processed(ctx, user=None):
    if user is None:
        user = ctx.author.name

    await ctx.channel.send(strings['process_check']['status']['checking'])
    if not opted_in(user=user):
        return await ctx.channel.send(strings['process_check']['status']['not_opted_in'])
    await ctx.channel.send(strings['process_check']['status']['opted_in'])
    return


def opted_in(user=None, id=None):
    if id is None:
        get_user = "SELECT `opted_in`, `username` FROM `users` WHERE  `username`=%s;"
    else:
        get_user = "SELECT `opted_in`, `username` FROM `users` WHERE  `user_id`=%s;"
        user = id

    cursor_summer.execute(get_user, (user, ))
    results = cursor_summer.fetchall()
    try:
        if results[0][0] != 1:
            return False
    except IndexError:
        return False
    return results[0][1]


def get_messages(table_name):
    get_messages = "SELECT `contents`, `channel_id` FROM `%s` ORDER BY TIME DESC"
    cursor_summer.execute(get_messages, (table_name, ))
    results = cursor_summer.fetchall()
    messages = []
    channels = []

    for x in range(0, len(results)):
        messages.append(results[x][0])
        channels.append(results[x][1])

    return messages, channels


def get_channel(id):
    for server in client.guilds:
        for channel in server.channels:
            if str(channel.id) == str(id):
                return channel
    return None


def channel_allowed(id, existing_channel, nsfw=False):

    channel = get_channel(int(id))

    for x in range(0, len(disabled_groups)):
        if str(channel.category).lower() == str(disabled_groups[x]).lower():
            return False

    if nsfw:
        if not existing_channel.is_nsfw():
            return False
        if channel.is_nsfw():
            return True
        else:
            return False  # this is because if NSFW is true, we only want stuff from NSFW chats
    else:
        if channel.is_nsfw():
            return False  # this is to prevent NSFW messages being included in SFW chats

    return True


async def save_markov(model, user_id):
    save = "INSERT INTO `markovs` (`user`, `markov_json`) VALUES (%s, %s);"
    save_update = "UPDATE `markovs` SET `markov_json`=%s WHERE `user`=%s;"

    try:
        cursor_summer.execute(save, (user_id, model.to_json()))
    except mysql.connector.errors.IntegrityError:
        cursor_summer.execute(save_update, (model.to_json(), user_id))
    cnx_summer.commit()
    return


@client.command()
async def markov_server(ctx, nsfw=0, selected_channel=None):
    output = await ctx.channel.send(content=strings['markov']['title'] + strings['emojis']['markov'])

    await output.edit(content=output.content + "\n" + strings['markov']['status']['messages'])
    async with ctx.channel.typing():
        text = []
        if nsfw == "True":
            nsfw = True
        elif nsfw == "False":
            nsfw = False
        nsfw = bool(nsfw)

        print(selected_channel)
        for server in client.guilds:
            for member in server.members:
                username = opted_in(id=member.id)
                if username is not False:
                    messages, channels = get_messages(username)
                    for x in range(0, len(messages)):
                        if channel_allowed(channels[x], ctx.message.channel, nsfw):
                            if selected_channel is not None:
                                if get_channel(int(channels[x])).name == selected_channel:
                                    text.append(messages[x])
                            else:
                                text.append(messages[x])

        length = len(text)

        text1 = ""
        for x in range(0, len(text)):
            text1 += str(text[x]) + "\n"

        try:
            await output.edit(content=output.content + strings['emojis']['success'] + "\n" + strings['markov']['status']['building_markov'])
            # text_model = POSifiedText(text)
            text_model = markovify.NewlineText(text, state_size=3)
        except KeyError:
            return ctx.channel.send('Not enough data yet, sorry!')
        await output.edit(content=output.content + strings['emojis']['success'] + "\n" + strings['markov']['status']['making'])
        text = text_model.make_short_sentence(140)
        attempt = 0
        while(True):
            attempt += 1
            if attempt >= 10:
                return await ctx.channel.send(content=strings['markov']['errors']['failed_to_generate'])
            message_formatted = str(text)
            if message_formatted != "None":
                break

        em = discord.Embed(
            title=strings['markov']['output']['title_server'], description=message_formatted)

        em.set_footer(strings['markov']['output']['footer'])
        await output.delete()
        output = await ctx.channel.send(embed=em, content=None)
    return await delete_option(client, ctx, output, client.get_emoji(strings['emoji']['delete']) or "❌")


@client.command()
async def markov(ctx, nsfw=0, selected_channel=None):
    output = await ctx.channel.send(content=strings['markov']['title'] + strings['emojis']['markov'])

    await output.edit(content=output.content + "\n" + strings['markov']['status']['messages'])
    async with ctx.channel.typing():
        username = opted_in(id=ctx.author.id)
        nsfw = bool(nsfw)
        if not username:
            return await output.edit(content=output.content + strings['markov']['errors']['not_opted_in'])
            return await ctx.channel.send()
        messages, channels = get_messages(username)
        text = []

        for x in range(0, len(messages)):
            if channel_allowed(channels[x], ctx.message.channel, nsfw):
                if selected_channel is not None:
                    if get_channel(int(channels[x])).name == selected_channel:
                        text.append(messages[x])
                else:
                    text.append(messages[x])

        text1 = ""
        for x in range(0, len(text)):
            text1 += str(text[x]) + "\n"

        try:
            await output.edit(content=output.content + strings['emojis']['success'] + "\n" + strings['markov']['status']['building_markov'])
            # text_model = POSifiedText(text)
            text_model = markovify.NewlineText(text, state_size=3)
        except KeyError:
            return ctx.channel.send('Not enough data yet, sorry!')

        await output.edit(content=output.content + strings['emojis']['success'])

        attempt = 0
        await output.edit(content=output.content + strings['emojis']['success'] + "\n" + strings['markov']['status']['analytical_data'])

        while(True):
            attempt += 1
            if attempt >= 10:
                await output.delete()
                return await ctx.channel.send(content=strings['markov']['errors']['failed_to_generate'])
            new_sentance = text_model.make_short_sentence(140)
            message_formatted = str(new_sentance)
            if message_formatted != "None":
                break

        em = discord.Embed(title=str(ctx.message.author) + strings['emojis']['markov'], description=message_formatted)
        em.set_footer(text=strings['markov']['output']['footer'])
        await output.delete()
    output = await ctx.channel.send(embed=em, content=None)
    return await delete_option(client, ctx, output, client.get_emoji(strings['emojis']['delete']) or "❌")


async def get_blacklist(user_id):
    get = "SELECT blacklist FROM blacklists WHERE user_id = %s"
    cursor_summer.execute(get, (user_id, ))
    resultset = cursor_summer.fetchall()
    return resultset[0]


@client.command()
async def blacklist(ctx, command=None, word=None):
    """
    Prevents words from being shown publicly through methods such as markov and markov_server. 
    Note: they will still be logged, and this just prevents them being shown in chat.

    Command: option to use
    Word: Word to add or remove from blacklist
    """
    await ctx.message.remove()
    if command is None:
        return await ctx.channel.send(content="""
No subcommand selected - please enter a subcommand for your blacklist.

?blacklist add [word] : Add word to blacklist
?blacklist remove [word] : Remove word from blacklist
?blacklist get : Get PM of current blacklist
			""")

    if command == "add":
        if word is None:
            return await ctx.channel.send(strings['blacklist']['status']['no_word'])
        msg = await ctx.channel.send(content=strings['blacklist']['status']['adding'])
        # TODO :Insert logic here
    elif command == "remove":
        if word is none:
            return await ctx.channel.send(strings['blacklist']['status']['no_word'])
        msg = await ctx.channel.send(content=strings['blacklist']['status']['removing'])
        # TODO: Insert logic here

    elif command == "get":
        await ctx.channel.send(content="#TODO")
    else:
        return await ctx.channel.send(content="""
No subcommand selected - please enter a subcommand for your blacklist.

?blacklist add [word] : Add word to blacklist
?blacklist remove [word] : Remove word from blacklist
?blacklist get : Get PM of current blacklist
			""")

    await msg.edit(content=strings['blacklist']['status']['complete'])


async def build_data_profile(name, member, guild):
    print("Initialising data tracking for " + name)
    for summer_channel in guild.text_channels:
        adding = True
        for x in range(0, len(disabled_groups)):
            if summer_channel.category.name.lower() == disabled_groups[x].lower():
                adding = False
                break

        if adding:
            print(name + " > in > " + summer_channel.name)
            messages_tocheck = await summer_channel.history(limit=50000).flatten()
            print(name + " > processing > " + summer_channel.name)
            for message in messages_tocheck:
                if message.author == member:
                    try:
                        cursor_summer.execute(add_message_custom, (name, int(message.id), str(
                            message.channel.id), message.created_at.strftime('%Y-%m-%d %H:%M:%S'), message.content,))
                    except mysql.connector.errors.DataError:
                        print("Couldn't insert, probs a time issue")
                    except mysql.connector.errors.IntegrityError:
                        pass
            cnx_summer.commit()


async def delete_option(bot, ctx, message, delete_emoji, timeout=60):
    """Utility function that allows for you to add a delete option to the end of a command.
    This makes it easier for users to control the output of commands, esp handy for random output ones."""
    await message.add_reaction(delete_emoji)

    def check(r, u):
        return str(r) == str(delete_emoji) and u == ctx.author and r.message.id == message.id

    try:
        await bot.wait_for("reaction_add", timeout=timeout, check=check)
        await message.remove_reaction(delete_emoji, bot.user)
        await message.remove_reaction(delete_emoji, ctx.author)
        em = discord.Embed(title=str(ctx.message.author) +
                           " deleted message", description="User deleted this message.")

        return await message.edit(embed=em)
    except:
        await message.remove_reaction(delete_emoji, bot.user)
client.run(token)