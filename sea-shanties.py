import discord
from discord.ext import commands, tasks
import wavelink
import asyncio
import json

intents = discord.Intents.default()
intents.voice_states = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

MOVE_AFTER_JOIN_CHANNEL_ID = 1352702271489703988
SPECIFIC_USER_ID = 136707204907663360
user_join_timers = {}

# Music Queue Dictionary
music_queues = {}

# Load settings from a JSON file
def load_settings():
    try:
        with open("settings.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        # If the file doesn't exist, use default values
        return {"move_delay_seconds": 30, "prank_enabled": True}

# Save settings to a JSON file
def save_settings():
    settings = {"move_delay_seconds": move_delay_seconds, "prank_enabled": prank_enabled}
    with open("settings.json", "w") as f:
        json.dump(settings, f)

# ---------------- Lavalink Setup ----------------
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    await wavelink.NodePool.create_node(
        bot=bot,
        host='127.0.0.1',
        port=2333,
        password='youshallnotpass'
    )

    # Load settings on startup
    global move_delay_seconds, prank_enabled
    settings = load_settings()
    move_delay_seconds = settings.get("move_delay_seconds", 30)
    prank_enabled = settings.get("prank_enabled", True)

# ---------------- Move User Feature ----------------
@bot.event
async def on_voice_state_update(member, before, after):
    if not prank_enabled:
        return  # Prank disabled

    if before.channel != after.channel and after.channel:
        if member.id == SPECIFIC_USER_ID:
            if member.id in user_join_timers:
                user_join_timers[member.id].cancel()
            task = asyncio.create_task(move_user_after_delay(member, MOVE_AFTER_JOIN_CHANNEL_ID, move_delay_seconds))
            user_join_timers[member.id] = task
    if after.channel is None:
        if member.id in user_join_timers:
            user_join_timers[member.id].cancel()
            del user_join_timers[member.id]

async def move_user_after_delay(member, target_channel_id, delay):
    await asyncio.sleep(delay)

    if not member.voice or not member.voice.channel:
        return

    original_channel = member.voice.channel

    # Find a text channel to send countdown
    text_channel = None
    for channel in member.guild.text_channels:
        if channel.permissions_for(member.guild.me).send_messages:
            text_channel = channel
            break

    if text_channel:
        await text_channel.send(f"⚠️ {member.mention}, you will be moved in 5 seconds...")
        for i in range(5, 0, -1):
            await text_channel.send(f"⏳ Moving in {i}...")
            await asyncio.sleep(1)

    if member.voice and member.voice.channel == original_channel:
        target_channel = member.guild.get_channel(target_channel_id)
        await member.move_to(target_channel)

        if text_channel:
            await text_channel.send(f"🔁 {member.mention} moved to temp channel. Returning in 5 seconds...")

        await asyncio.sleep(5)

        if member.voice and member.voice.channel == target_channel:
            await member.move_to(original_channel)
            if text_channel:
                await text_channel.send(f"✅ {member.mention} returned to original channel.")

# ---------------- Music Commands ----------------
@bot.command(name='YOHO')
async def play_music(ctx, *, query: str):
    vc = ctx.author.voice
    if not vc:
        return await ctx.send("You must be in a voice channel.")

    guild_id = ctx.guild.id

    if not ctx.voice_client:
        player: wavelink.Player = await vc.channel.connect(cls=wavelink.Player)
        music_queues[guild_id] = []
        player.queue = music_queues[guild_id]
        player.ctx = ctx

        async def after_playing(track, error):
            if error:
                print("Playback error:", error)
            await play_next(ctx.guild)

        player.after_playing = after_playing
    else:
        player = ctx.voice_client

    if not query.startswith("http"):
        query = f"ytsearch:{query}"

    track = await wavelink.YouTubeTrack.search(query, return_first=True)
    if not player.is_playing():
        await player.play(track)
        await ctx.send(f"🎶 Now playing: {track.title}")
    else:
        player.queue.append(track)
        await ctx.send(f"✅ Added to queue: {track.title}")

async def play_next(guild):
    player = guild.voice_client
    if player and hasattr(player, 'queue') and player.queue:
        next_track = player.queue.pop(0)
        await player.play(next_track)
        await player.ctx.send(f"🎵 Now playing: {next_track.title}")
    else:
        await asyncio.sleep(300)  # Wait 5 minutes before disconnecting
        if player and not player.is_playing():
            await player.disconnect()
            await player.ctx.send("🛑 Disconnected due to inactivity.")

@bot.command()
async def skip(ctx):
    player = ctx.voice_client
    if player and player.is_playing():
        await player.stop()
        await ctx.send("⏭️ Skipped current song.")
    else:
        await ctx.send("Nothing is playing right now.")

@bot.command()
async def pause(ctx):
    player = ctx.voice_client
    if player and player.is_playing():
        await player.pause()
        await ctx.send("⏸️ Paused music.")
    else:
        await ctx.send("Nothing is playing.")

@bot.command()
async def stop(ctx):
    player = ctx.voice_client
    if player:
        player.queue.clear()
        await player.disconnect()
        await ctx.send("🛑 Stopped music and cleared the queue.")
    else:
        await ctx.send("I'm not in a voice channel.")

# ---------------- Configuration Commands ----------------

@bot.command()
async def setdelay(ctx, seconds: int):
    global move_delay_seconds
    if seconds < 1 or seconds > 600:
        return await ctx.send("⏱️ Please choose a value between 1 and 600 seconds.")
    move_delay_seconds = seconds
    save_settings()  # Save the updated delay time
    await ctx.send(f"✅ Move delay time set to {seconds} seconds.")

@bot.command()
async def toggleprank(ctx):
    global prank_enabled
    prank_enabled = not prank_enabled
    save_settings()  # Save the updated prank setting
    status = "enabled" if prank_enabled else "disabled"
    await ctx.send(f"🎭 Move prank feature is now **{status}**.")