import os
import discord
from discord.ext import commands, tasks
import requests
from keep_alive import keep_alive
import json
import datetime
from discord import FFmpegPCMAudio
from google.cloud import texttospeech
import re
import tarfile
import shutil
import edge_tts

RTO_CHANNEL_ID = 1341573057952878674
# Load secrets from environment variables
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ERLC_API_KEY = os.getenv("ERLC_API_KEY")
SERVER_KEY = os.getenv("SERVER_KEY")
SSD_ACTIVE = False

FFMPEG_DIR = os.path.join(os.getcwd(), "ffmpeg")
FFMPEG_BINARY = os.path.join(FFMPEG_DIR, "ffmpeg")
FFMPEG_URL = "https://github.com/lyricalnovaa/ASRP/releases/download/DiscordFFMPEG/ffmpeg-release-amd64-static.tar.xz?raw=true"

def ensure_ffmpeg():
    if os.path.exists(FFMPEG_BINARY):
        return FFMPEG_BINARY

    os.makedirs(FFMPEG_DIR, exist_ok=True)
    tar_path = os.path.join(FFMPEG_DIR, "ffmpeg.tar.xz")

    print("Downloading FFmpeg tar.xz release...")
    r = requests.get(FFMPEG_URL, stream=True)
    r.raise_for_status()
    with open(tar_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)

    print("Extracting ffmpeg binary from tar...")
    with tarfile.open(tar_path, "r:xz") as tar:
        for member in tar.getmembers():
            if os.path.basename(member.name) == "ffmpeg":
                tar.extract(member, FFMPEG_DIR)
                extracted_path = os.path.join(FFMPEG_DIR, member.name)
                shutil.move(extracted_path, FFMPEG_BINARY)
                break

    os.remove(tar_path)
    os.chmod(FFMPEG_BINARY, 0o755)
    print("FFmpeg ready!")
    return FFMPEG_BINARY

ensure_ffmpeg()


# Check if TOKEN is set correctly
if TOKEN is None:
    raise ValueError("DISCORD_BOT_TOKEN environment variable is not set!")

# Base URL for ER:LC API
BASE_URL = "https://api.policeroleplay.community/v1"
HR_ROLE_IDS = {
    1342314882002845706,  #ASRP HR
    1342032442143543296, 
    1343642362546618496,
    1342347037907095606,  #FSFD HR
    1342349329045651542,  #ARDOT HR
    1342350523130581077,  #FSPD HR
    1344866546136256635,  #VBPD HR
    1342326135433855081,  #CCD HR
    1342061849490886713,  #ASP HR
    1342351211168272398,  #CCSO HR
    1342348906440425556   #DPS HR
}
DISPATCH_ROLE_ID = 1341969857884848189
POLICE_ROLE_ID = 1341966121976336404
STATE_POLICE_ROLE_ID = 1341966256768679977
SHERIFF_ROLE_ID = 1341965751325687838

intents = discord.Intents.default()
intents.message_content = True  # Enable the message content intent
intents.members = True  # Enable server member intent, if needed
intents.presences = True  # Enable presence intent, if needed
intents.voice_states = True 

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
# Restrict bot to be used only in a specific server
guild_whitelist = [
    "1341314653372022804", "1342061849352605806", "1342067615371231262",
    "1342326135362682940", "1342347037819273247", "1342349328584409218",
    "1342350523046690836", "1342351211097096213", "1342351211097096213",
    "1342348906289299466", "1343642362148163665"
]


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    for guild in bot.guilds:
        print(f"Connected to: {guild.name} ({guild.id})")
        vc_channel = guild.get_channel(RTO_CHANNEL_ID)
        if vc_channel and not bot.voice_clients:
            await vc_channel.connect()
            print(f"Joined VC: {vc_channel.name}")

@bot.event
async def on_member_update(before, after):
    """Give a role when a user gets the Verified role."""
    VERIFIED_ROLE_ID = 1341600703583490150  # The "Verified" role ID
    NEW_ROLE_1_ID = 1341971349320630352  # Role to assign after verification
    NEW_ROLE_2_ID = 1341972650330685564
    GUILD_ID = 1341314653372022804
    guild = after.guild

    # Check if the user is in the correct guild
    if guild.id != GUILD_ID:
        return

    # Get the roles from before and after the update
    before_roles = set(before.roles)
    after_roles = set(after.roles)

    verified_role = guild.get_role(VERIFIED_ROLE_ID)
    new_role_1 = guild.get_role(NEW_ROLE_1_ID)
    new_role_2 = guild.get_role(NEW_ROLE_2_ID)
    # Check if the user has just been given the Verified role
    if verified_role in after_roles and verified_role not in before_roles:
        if new_role_1 and new_role_2:
            await after.add_roles(new_role_1, new_role_2)
            print(
                f"Added {new_role_1.name} and {new_role_2.name} to {after.name}"
            )
        else:
            print("One or both roles not found!")


@bot.check
async def globally_block_dms(ctx):
    return ctx.guild and str(ctx.guild.id) in guild_whitelist


def is_hr():
    """Custom check to ensure the user has one of the 'HR' roles."""

    def predicate(ctx):
        return any(role.id in HR_ROLE_IDS for role in ctx.author.roles)

    return commands.check(predicate)


DEPARTMENT_INVITES = {
    "ASP": "https://discord.gg/pG3pekyrnA",
    "Dispatch": "https://discord.gg/wMdC5dpPvF",
    "FSFD": "https://discord.gg/6zsnUUEXvW",
    "Staff": "We have no Discord Server For Staff"
    # Add more departments as needed
}

mod_notes = {}


@bot.command()
@commands.has_role('ASRP | HR Team')
async def speccodes(ctx):
    """Displays the list of available spec codes."""
    embed = discord.Embed(title="🚨 Special Codes 🚨",
                          color=discord.Color.blue())
    embed.add_field(name="",
                    value='10-86: Switch to a secondary channel',
                    inline=False)
    embed.add_field(name="",
                    value='10-SWAT: Pre-call up for SWAT',
                    inline=False)
    embed.add_field(name="", value='11-SWAT: Call up for SWAT', inline=False)
    embed.add_field(name="Codes: ",
                    value='\nCode 1 No Lights and Sirens',
                    inline=False)
    embed.add_field(name="", value='Code 2 Lights No Sirens', inline=False)
    embed.add_field(name="", value='Code 3 Lights and Sirens', inline=False)
    await ctx.send(embed=embed)


@bot.command()
@commands.has_role('ASRP | HR Team')
async def codes(ctx):
    """Command to send all priority codes in an embed and ping @everyone."""

    try:
        # Open and read the codes from the text file
        with open("codes.txt", "r") as file:
            codes = file.readlines()

        # Clean up the codes list (remove any extra whitespace/newlines)
        codes = [code.strip() for code in codes]

        # Split codes into chunks of 1024 characters or fewer
        chunks = []
        current_chunk = ""

        for code in codes:
            # Add code to the current chunk if it doesn't exceed the 1024 character limit
            if len(current_chunk) + len(code) + 1 <= 1024:  # +1 for newline
                current_chunk += code + "\n"
            else:
                # If adding the code exceeds the limit, push the current chunk and start a new one
                chunks.append(current_chunk.strip())
                current_chunk = code + "\n"

        # Add the last chunk if there's any leftover data
        if current_chunk:
            chunks.append(current_chunk.strip())

        # Create and send the embeds
        for i, chunk in enumerate(chunks):
            embed = discord.Embed(title="🚨 Priority Codes 🚨" if i == 0 else "",
                                  description="",
                                  color=discord.Color.blue())
            embed.add_field(name="", value=chunk, inline=False)

            # Send the message with @everyone ping
            if i == 0:
                await ctx.send(f"@everyone Here are all the priority codes:",
                               embed=embed)
            else:
                await ctx.send(embed=embed)

    except FileNotFoundError:
        await ctx.send(
            "🚫 The codes file 'codes.txt' was not found. Please check the file location."
        )
    except Exception as e:
        await ctx.send(f"🚫 An error occurred: {str(e)}")

@bot.command()
async def appopen(ctx, app_name: str, department: str):
    # Find the announcements channel
    announcements_channel = discord.utils.get(ctx.guild.text_channels, name='「📣」𝖠nnouncements')

    if announcements_channel is None:
        await ctx.send("Announcements channel not found!")
        return

    # Create an embed
    embed = discord.Embed(title=f"{app_name} Applications Open!", description=f"{app_name} is now open! Please apply for {department} if you would like to join!", color=discord.Color.green())

    # Send the embed to the announcements channel with @everyone ping
    await announcements_channel.send("@everyone", embed=embed)
    await ctx.send("Application announcement sent!")

@bot.command()
@is_hr()
@commands.has_permissions(manage_messages=True)
async def appaccept(ctx, user: discord.User, department: str, *, notes: str):
    """Accepts an application and sends a DM to the user while saving the moderator note."""

    department_invite = DEPARTMENT_INVITES.get(department,
                                               "No invite available")

    try:
        embed = discord.Embed(
            title="Congratulations!",
            description=
            f"Your application has been accepted into **{department}**! 🎉\n"
            f"You will get your roles shortly!\n\n"
            f"Make sure to join the department's Discord: {department_invite}",
            color=discord.Color.green())
        embed.add_field(name="Moderator Note", value=notes, inline=False)
        embed.set_footer(text=f"- ASRP | {department}")
        await user.send(embed=embed)

        save_mod_note(user.id, "appaccept", notes)
        await ctx.send(f"Application accepted for {user.name} in {department}."
                       )

    except discord.Forbidden:
        await ctx.send(
            f"Could not send DM to {user.name}. Please ensure they have DMs open."
        )


@bot.command()
@is_hr()
@commands.has_permissions(manage_messages=True)
async def appdenied(ctx, user: discord.User, department: str, *, notes: str):
    """Denies an application and sends a DM to the user while saving the moderator note."""

    try:
        embed = discord.Embed(
            title="Unfortunately, Your application has been denied",
            description=
            f"Your application has been denied into **{department}**. 😞",
            color=discord.Color.red())
        embed.add_field(name="Moderator Note", value=notes, inline=False)
        embed.set_footer(text=f"- ASRP | {department}")
        await user.send(embed=embed)

        save_mod_note(user.id, "appdenied", notes)
        await ctx.send(f"Application denied for {user.name} in {department}.")

    except discord.Forbidden:
        await ctx.send(
            f"Could not send DM to {user.name}. Please ensure they have DMs open."
        )


@bot.command(aliases=["ipass"])
@is_hr()
@commands.has_permissions(manage_messages=True)
async def interviewpass(ctx, user: discord.User, department: str):
    """Notifies a user that they have passed their interview."""
    try:
        embed = discord.Embed(
            title="Congratulations!",
            description=
            f"You have passed your interview for **{department}**! 🎉\n"
            f"You will receive further instructions soon.",
            color=discord.Color.green())
        embed.set_footer(text=f"- ASRP | {department}")
        await user.send(embed=embed)
        await ctx.send(
            f"Interview passed notification sent to {user.name} for {department}."
        )
    except discord.Forbidden:
        await ctx.send(
            f"Could not send DM to {user.name}. Please ensure they have DMs open."
        )


@bot.command(aliases=["ifail"])
@is_hr()
@commands.has_permissions(manage_messages=True)
async def interviewfail(ctx, user: discord.User, department: str):
    """Notifies a user that they have failed their interview."""
    try:
        embed = discord.Embed(
            title="Unfortunately, You did not pass",
            description=
            f"You did not pass your interview for **{department}**. 😞",
            color=discord.Color.red())
        embed.set_footer(text=f"- ASRP | {department}")
        await user.send(embed=embed)
        await ctx.send(
            f"Interview fail notification sent to {user.name} for {department}."
        )
    except discord.Forbidden:
        await ctx.send(
            f"Could not send DM to {user.name}. Please ensure they have DMs open."
        )


@bot.command()
@is_hr()
@commands.has_permissions(manage_messages=True)
async def partnershipaccept(ctx, user: discord.User, community_name: str, *,
                            notes: str):
    """Accepts a partnership request and sends a DM while saving the moderator note."""

    try:
        embed = discord.Embed(
            title="Congratulations! 🎉",
            description=
            f"Your partnership request with **{community_name}** has been accepted! 🎊\n\n"
            f"We look forward to working together. A representative will reach out soon for further coordination.",
            color=discord.Color.green())
        embed.add_field(name="Moderator Note", value=notes, inline=False)
        embed.set_footer(text="- ASRP Partnerships")
        await user.send(embed=embed)

        save_mod_note(user.id, "partnershipaccept", notes)
        await ctx.send(
            f"Partnership accepted for {user.name} with {community_name}. Please send your Advertisement."
        )

    except discord.Forbidden:
        await ctx.send(
            f"Could not send DM to {user.name}. Please ensure they have DMs open."
        )


@bot.command()
@is_hr()
@commands.has_permissions(manage_messages=True)
async def partnershipdeny(ctx, user: discord.User, community_name: str, *,
                          notes: str):
    """Denies a partnership request and sends a DM while saving the moderator note."""

    try:
        embed = discord.Embed(
            title="Partnership Request Denied",
            description=
            f"Unfortunately, your partnership request with **{community_name}** has been denied. 😞",
            color=discord.Color.red())
        embed.add_field(name="Moderator Note", value=notes, inline=False)
        embed.set_footer(text="- ASRP Partnerships")
        await user.send(embed=embed)

        save_mod_note(user.id, "partnershipdeny", notes)
        await ctx.send(
            f"Partnership denied for {user.name} with {community_name}.")

    except discord.Forbidden:
        await ctx.send(
            f"Could not send DM to {user.name}. Please ensure they have DMs open."
        )


MOD_NOTES_FILE = "mod_notes.json"


def load_mod_notes():
    try:
        with open(MOD_NOTES_FILE, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_mod_notes(mod_notes):
    with open(MOD_NOTES_FILE, "w") as file:
        json.dump(mod_notes, file, indent=4)


mod_notes = load_mod_notes()


@bot.command()
@is_hr()
@commands.has_permissions(manage_messages=True)
async def modnote(ctx, user: discord.User = None):
    """Retrieves all stored moderator notes for a specific user."""

    if user is None:
        await ctx.send("Please mention a user to check their moderator notes.")
        return

    user_notes = mod_notes.get(str(user.id), [])

    if not user_notes:
        await ctx.send(f"No moderator notes found for {user.name}.")
        return

    embed = discord.Embed(title=f"Moderator Notes for {user.name}",
                          color=discord.Color.blue())

    for command_type, note in user_notes:
        embed.add_field(name=f"{command_type.capitalize()} Note",
                        value=note,
                        inline=False)

    await ctx.send(embed=embed)


def save_mod_note(user_id, command_type, note):
    """Saves a moderator note for a user."""
    if user_id not in mod_notes:
        mod_notes[user_id] = []
    mod_notes[user_id].append((command_type, note))


@bot.command()
@is_hr()
async def promote(ctx, user: discord.User, roblox_id: int, old_role_id: int,
                  new_role_id: int, reason: str, notes: str,
                  approved_by: discord.User):
    """Promote a user and notify the staff team."""

    # Check if the user has the old role
    old_role = discord.utils.get(ctx.guild.roles, id=old_role_id)
    new_role = discord.utils.get(ctx.guild.roles, id=new_role_id)

    if old_role is None or new_role is None:
        await ctx.send("Invalid role IDs provided.")
        return

    # Add the new role to the user
    member = ctx.guild.get_member(user.id)
    if member:
        await member.add_roles(new_role)
        await member.remove_roles(old_role)

    # Build the embed to notify the staff team
    embed = discord.Embed(title="Role Promotion",
                          description=f"**{user.name}** has been promoted!",
                          color=discord.Color.green())
    embed.add_field(name="My Username:", value=ctx.author.name, inline=False)
    embed.add_field(name="My Discord ID:", value=ctx.author.id, inline=False)
    embed.add_field(name="Their Username:", value=user.name, inline=False)
    embed.add_field(name="Their Discord ID:", value=user.id, inline=False)

    # Assuming you also get the Roblox ID from a custom system or database
    # Example: Roblox ID can be fetched here
    embed.add_field(name="Their Roblox ID:", value=roblox_id, inline=False)

    embed.add_field(name="Old Rank:", value=old_role.name, inline=False)
    embed.add_field(name="New Rank:", value=new_role.name, inline=False)
    embed.add_field(name="Reason:", value=reason, inline=False)
    embed.add_field(name="Notes:", value=notes, inline=False)
    embed.add_field(name="Approved by:", value=approved_by.name, inline=False)

    # Mention the staff team (replace `@Staff Team` with actual staff role)
    staff_role = discord.utils.get(ctx.guild.roles, name="Staff Team")
    if staff_role:
        embed.set_footer(text=f"Staff Team: {staff_role.mention}")

    await ctx.send(f"@{staff_role.name} Role promotion details:", embed=embed)


@bot.command()
async def servers(ctx):
    guilds = "\n".join([f"{guild.name} ({guild.id})" for guild in bot.guilds])
    await ctx.send(f"I'm in these servers:\n{guilds}")


@bot.command(aliases=["js", "jserver"])
@commands.has_permissions(
    administrator=True)  # Ensure only admins can use this command
async def join_server(ctx, guild_id: str):
    """Generates an invite link for the bot to join a whitelisted server."""
    if guild_id in guild_whitelist:
        permissions = 8  # Administrator permissions (modify as needed)
        invite_link = f"https://discord.com/oauth2/authorize?client_id={bot.user.id}&permissions={permissions}&scope=bot"
        embed = discord.Embed(
            title="Bot Invite Link",
            description=
            f"Use this link to invite the bot to the server with ID: `{guild_id}`\n[Click here to invite]({invite_link})",
            color=discord.Color.green())
        await ctx.send(embed=embed)
    else:
        await ctx.send("This server is not whitelisted for bot joining.")


@bot.command(aliases=["SSP", "SSUP"])
@is_hr()
async def ssu_poll(ctx, votes_required: int):
    """Starts an SSU poll that requires a certain number of votes."""

    embed = discord.Embed(
        title="SSU Poll - Vote Now!",
        description=f"{ctx.author.mention} has started an SSU poll!\n\n"
        f"React with ✅ to vote for an SSU.\n"
        f"Votes required: **{votes_required}**",
        color=discord.Color.blue())

    poll_message = await ctx.send("@here", embed=embed)
    await poll_message.add_reaction("✅")  # Add reaction for voting

    # Wait for reactions and count votes
    def check(reaction, user):
        return reaction.message.id == poll_message.id and str(
            reaction.emoji) == "✅" and not user.bot

    vote_count = 0
    while vote_count < votes_required:
        reaction, user = await bot.wait_for("reaction_add", check=check)
        vote_count = sum(r.count - 1 for r in poll_message.reactions
                         if str(r.emoji) == "✅")

    # SSU approved, send notification
    embed = discord.Embed(
        title="Server Start Up Notification",
        description=
        f"✅ SSU Approved! {votes_required} votes reached!\n{ctx.author.mention} has started the session.",
        color=discord.Color.green())
    embed.add_field(name="Server Information",
                    value="■▬✶▬▬▬▬▬▬▬◢◤◆◥◣▬▬▬▬▬▬▬✶▬■",
                    inline=False)
    embed.add_field(name="Server Owner", value="guavajuice3006", inline=True)
    embed.add_field(name="Server Name",
                    value="Arkansas State Roleplay I VC Only",
                    inline=True)
    embed.add_field(name="Server Join Code", value="ARKSTATE", inline=True)
    embed.add_field(name="■▬✶▬▬▬▬▬▬▬◢◤◆◥◣▬▬▬▬▬▬▬✶▬■",
                    value="\u200b",
                    inline=False)

    await ctx.send("@here", embed=embed)


@bot.command()
@is_hr()
@commands.has_permissions(kick_members=True)
async def kick(ctx, user: discord.Member, *, reason: str):
    """Kicks a user and notifies them."""
    try:
        embed = discord.Embed(
            title="ASRP Server Kick",
            description=
            f"**Action:** Kick\n**Reason:** {reason}\n**Timeframe to rejoin:** 30 minutes\n",
            color=discord.Color.orange())
        await user.send(embed=embed)
    except discord.Forbidden:
        await ctx.send(
            f"Could not send DM to {user.name}. Please ensure they have DMs open."
        )
    await user.kick(reason=reason)
    await ctx.send(f"{user.name} has been kicked. Reason: {reason}")


BAN_SERVER_INVITE = "https://discord.gg/Dx6Y9nnDUJ"


@bot.command()
@is_hr()
@commands.has_permissions(ban_members=True)
async def ban(ctx, user: discord.Member, *, reason: str):
    """Bans a user and notifies them."""
    try:
        embed = discord.Embed(
            title="ASRP Server Ban",
            description=
            f"**Action:** Ban\n**Reason:** {reason}\n**Ban Server Invite:** [Join Here] {BAN_SERVER_INVITE}",
            color=discord.Color.red())
        await user.send(embed=embed)
    except discord.Forbidden:
        await ctx.send(
            f"Could not send DM to {user.name}. Please ensure they have DMs open."
        )
    await user.ban(reason=reason)
    await ctx.send(f"{user.name} has been banned. Reason: {reason}")


@bot.command()
@is_hr()
async def SSD(ctx):
    """Shuts down the ER:LC private server, starts peace and priority timers, and locks all VC's in the given category."""
    category_id = 1341572204420268063
    # Fetch the category
    category = discord.utils.get(ctx.guild.categories, id=category_id)
    if not category:
        return await ctx.send("Invalid category ID. Please update with a valid category.")

    # Lock all voice channels in the category
    locked_vc_id = 1341573539643265106
    # Lock all voice channels in the category
    restricted_roles = ["Unverified", "Role2", "Role3"]  # Replace with actual role names or IDs

    # Lock all voice channels in the category and hide the category from restricted roles
    for channel in category.voice_channels:
        if channel.id != locked_vc_id:  # Lock all except the locked VC
            await channel.set_permissions(ctx.guild.default_role, connect=False)# Locking VC for default users
    locked_vc = discord.utils.get(ctx.guild.voice_channels, id=locked_vc_id)
    if locked_vc:
        await locked_vc.set_permissions(ctx.guild.default_role, connect=False)  # Explicitly keep it locked


    for role_name in restricted_roles:
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        if role:
            await category.set_permissions(role, view_channel=False)

    headers = {
        "Server-Key": f"{SERVER_KEY}",
        "Content-Type": "application/json"  # Add the content-type header
    }

    # Create the embed with the server shutdown information
    embed = discord.Embed(
        title="Server Shutdown Notification",
        description=(
            f"A Server Shutdown has occurred.\n"
            f"{ctx.author} has shut down the session. Thanks for playing!!"
        ),
        color=discord.Color.blue()
    )

    # Add server information to the embed
    embed.add_field(name="Server Information",
                    value="■▬✶▬▬▬▬▬▬▬◢◤◆◥◣▬▬▬▬▬▬▬✶▬■",
                    inline=False)
    embed.add_field(name="Server Owner", value="guavajuice3006", inline=True)
    embed.add_field(name="Server Name",
                    value="Arkansas State Roleplay I VC Only",
                    inline=True)
    embed.add_field(name="Server Join Code", value="ARKSTATE", inline=True)
    embed.add_field(name="Notes", value="All Roleplay VC's have been locked!", inline=False)
    embed.add_field(name="■▬✶▬▬▬▬▬▬▬◢◤◆◥◣▬▬▬▬▬▬▬✶▬■",
                    value="\u200b",
                    inline=False)

    await ctx.send("@here", embed=embed)


@bot.command()
@is_hr()
async def SSU(ctx):
    category_id = 1341572204420268063
    # Fetch the category
    category = discord.utils.get(ctx.guild.categories, id=category_id)
    if not category:
        return await ctx.send("Invalid category ID. Please update with a valid category.")
    locked_vc_id = 1341573539643265106
    # Lock all voice channels in the category
    restricted_roles = ["Unverified"]  # Replace with actual role names or IDs

    # Lock all voice channels in the category and hide the category from restricted roles
    for channel in category.voice_channels:
        if channel.id != locked_vc_id:  # Lock all except the locked VC
            await channel.set_permissions(ctx.guild.default_role, connect=True)# Locking VC for default users
    locked_vc = discord.utils.get(ctx.guild.voice_channels, id=locked_vc_id)
    if locked_vc:
        await locked_vc.set_permissions(ctx.guild.default_role, connect=False)  # Explicitly keep it locked

    for role_name in restricted_roles:
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        if role:
            await category.set_permissions(role, view_channel=False)
    # Add the Content-Type header as well
    headers = {
        "Server-Key": f"{SERVER_KEY}",
        "Content-Type": "application/json",
    }
    # Create the embed with the server startup information
    embed = discord.Embed(
        title="Server Start Up Notification",
        description=
        f"A Server Start Up has occurred.\n{ctx.author} has started the session.",
        color=discord.Color.blue())

    # Add server information to the embed
    embed.add_field(name="Server Information",
                    value="■▬✶▬▬▬▬▬▬▬◢◤◆◥◣▬▬▬▬▬▬▬✶▬■",
                    inline=False)
    embed.add_field(name="Server Owner", value="guavajuice3006", inline=True)
    embed.add_field(name="Server Name",
                    value="Arkansas State Roleplay I VC Only",
                    inline=True)
    embed.add_field(name="Server Join Code", value="ARKSTATE", inline=True)
    embed.add_field(name="Notes", value="All Roleplay VC's have been unlocked!", inline=False)
    embed.add_field(name="■▬✶▬▬▬▬▬▬▬◢◤◆◥◣▬▬▬▬▬▬▬✶▬■",
                    value="\u200b",
                    inline=False)

    # Send the embed to the same channel where the command was issued
    await ctx.send("@here", embed=embed)


@bot.command()
@is_hr()
async def apps(ctx):
    """Sends 7 embeds with application links for each department."""

    departments = [("Arkansas State Patrol (ASP)",
                    "https://forms.gle/k79pD4W9SL2igBa36"),
                   ("Fort Smith Police Department (FSPD)",
                    "https://forms.gle/xXGj69j9mLZEakJcA"),
                   ("Fort Smith Fire Department (FSFD)",
                    "https://forms.gle/mArtXkpCghyoQTgm7"),
                   ("Crawford County Sheriff Office (CCSO)",
                    "https://forms.gle/kPgc6Uo9Num919fC9"),
                   ("Arkansas Department of Transportation (ARDOT)",
                    "https://forms.gle/LRwzmcjNKcA72jNy7"),
                   ("Crawford County Dispatch (CCD)",
                    "https://forms.gle/fvD86WHo1oiuBAf8A")]

    for name, link in departments:
        embed = discord.Embed(
            title=f"{name} Application",
            description=f"Apply now by clicking [here]({link})!",
            color=discord.Color.blue())
        embed.set_footer(text="Thank you for your interest in joining!")
        await ctx.send(embed=embed)


@bot.command()
@is_hr()
async def ss(ctx):
    """Fetches and sends the server status."""
    headers = {"Server-Key": f"{SERVER_KEY}"}
    response = requests.get(f"{BASE_URL}/server", headers=headers)

    print("Raw API Response:", response.status_code,
          response.text)  # Debugging

    if response.status_code == 200:
        status_data = response.json()

        # Debugging: Print the extracted data
        print("Parsed Server Data:", status_data)

        # Extracting server data safely (defaulting to 'Unknown' or 'N/A' if missing)
        server_name = status_data.get("Name", "Unknown")
        current_players = status_data.get("CurrentPlayers", 0)
        max_players = status_data.get("MaxPlayers", 0)

        # Set session status based on the number of players
        session_status = "Shut Down" if current_players == 0 else "Started"

        # Embed message
        embed = discord.Embed(title="Server Status",
                              color=discord.Color.blue())
        embed.add_field(name="Server Name", value=server_name, inline=False)
        embed.add_field(name="Player Count",
                        value=f"{current_players}/{max_players}",
                        inline=True)
        embed.add_field(name="Session Status",
                        value=session_status,
                        inline=True)

        await ctx.send(embed=embed)
    else:
        await ctx.send(f"Failed to fetch server status: {response.text}")


@bot.command(aliases=['ps', 'pl'])
@is_hr()
async def pis(ctx):
    """Fetches and sends a list of players in the server."""
    headers = {"Server-Key": f"{SERVER_KEY}"}
    response = requests.get(f"{BASE_URL}/server/players", headers=headers)

    if response.status_code == 200:
        data = response.json()

        # Debug: Print the API response to check the structure
        print("Raw API Response:", data)

        if isinstance(data, list) and data:  # Ensure it's a non-empty list
            player_list = []
            for player in data:
                # Extract Player name and ID
                player_info = player.get('Player', 'Unknown')
                if ':' in player_info:
                    name, player_id = player_info.split(':',
                                                        1)  # Split name and ID
                else:
                    name, player_id = player_info, 'Unknown'

                # Extract Team and Callsign (if applicable)
                team = player.get('Team', 'Unknown')
                callsign = player.get('Callsign',
                                      None)  # Some teams may have a callsign

                # Format Team with Callsign (if exists)
                if callsign:
                    team_info = f"{team} ({callsign})"
                else:
                    team_info = team

                # Extract Role
                role = player.get('Permission', 'No Role')

                # Format the player info
                player_list.append(
                    f"**User:** {name} | **ID:** {player_id} | **Team:** {team_info} | **Role:** {role}"
                )

            embed = discord.Embed(title="Players in Server",
                                  description="\n".join(player_list),
                                  color=discord.Color.blue())
            await ctx.send(embed=embed)
        else:
            await ctx.send("No players currently in the server.")
    else:
        await ctx.send(f"Failed to fetch players: {response.text}")


@bot.command(aliases=['jl', 'jlogs'])
@is_hr()
async def joinlogs(ctx):
    """Fetches and sends the join logs."""
    headers = {"Server-Key": f"{SERVER_KEY}"}
    response = requests.get(f"{BASE_URL}/server/joinlogs", headers=headers)

    print("Raw API Response:", response.status_code,
          response.text)  # Debugging

    if response.status_code == 200:
        data = response.json()

        if isinstance(data, list) and data:  # Ensure it's a non-empty list
            log_messages = []
            for log in data:
                # Extract and clean player names (removing user IDs)
                player_raw = log.get(
                    "Player",
                    "Unknown")  # Fixed key name (was "player", now "Player")
                player = player_raw.split(
                    ":")[0] if ":" in player_raw else player_raw

                timestamp = log.get(
                    "Timestamp", "Unknown Time"
                )  # Fixed key name (was "timestamp", now "Timestamp")

                # Format the join log entry
                log_messages.append(
                    f"**Player:** {player} | **Joined at:** {timestamp}")

            embed = discord.Embed(title="Join Logs",
                                  description="\n".join(log_messages),
                                  color=discord.Color.blue())
            await ctx.send(embed=embed)
        else:
            await ctx.send("No join logs available.")
    else:
        await ctx.send(f"Failed to fetch join logs: {response.text}")


@bot.command(aliases=['pq', 'ql'])
# Assuming you have this decorator to check if the user has the HR role
async def playersinqueue(ctx):
    """Fetches and sends a list of players in the queue."""
    headers = {"Server-Key": f"{SERVER_KEY}"}
    response = requests.get(f"{BASE_URL}/server/queue", headers=headers)
    if response.status_code == 200:
        queue = response.json(
        )  # Directly assign the response to queue (no need for .get)
        if queue:
            queue_list = "\n".join([
                f"{player['username']} - {player['position']}"
                for player in queue
            ])
            embed = discord.Embed(title="Players in Queue",
                                  description=queue_list,
                                  color=discord.Color.blue())
            await ctx.send(embed=embed)
        else:
            await ctx.send("No players in the queue.")
    else:
        await ctx.send(f"Failed to fetch queue data: {response.text}")


@bot.command(aliases=['kill', 'kl', 'klogs'])
@is_hr()
async def kill_logs(ctx):
    """Fetches and sends the kill logs."""
    headers = {"Server-Key": f"{SERVER_KEY}"}
    response = requests.get(f"{BASE_URL}/server/killlogs", headers=headers)

    if response.status_code == 200:
        data = response.json()

        # Debugging: Print the raw API response to check the structure
        print("Raw API Response:",
              data)  # This will print the entire structure

        if isinstance(data, list) and data:  # Ensure it's a non-empty list
            kill_list = []
            for log in data:
                # Check if 'Weapon' or similar exists in the response
                print("Log Entry:",
                      log)  # Print individual log entries to debug

                # Extract Killer, Victim, and Timestamp
                killer_info = log.get('Killer', 'Unknown')
                victim_info = log.get('Killed', 'Unknown')
                timestamp = log.get('Timestamp', 'Unknown')

                # Check for 'Weapon' key (you can replace it with the correct key if it's different)
                weapon = log.get('Weapon', 'Unknown')

                # If 'Weapon' is not found, let's print out the available keys for each log entry
                if weapon == 'Unknown':
                    print(f"Available keys in this log: {log.keys()}"
                          )  # Debugging key names

                # Format the kill log info without user IDs
                kill_list.append(
                    f"**Killer:** {killer_info} | **Victim:** {victim_info} | **Time:** {timestamp} | **Weapon:** {weapon}"
                )

            embed = discord.Embed(title="Kill Logs",
                                  description="\n".join(kill_list),
                                  color=discord.Color.red())
            await ctx.send(embed=embed)
        else:
            await ctx.send("No kill logs available.")
    elif response.status_code == 404:
        await ctx.send(
            "Kill logs endpoint not found. Please check the server configuration."
        )
    else:
        await ctx.send(f"Failed to fetch kill logs: {response.text}")


@bot.command(aliases=['cmdlogs', 'cl'])
@is_hr()
async def command_logs(ctx):
    """Fetches and sends the command logs."""
    headers = {"Server-Key": f"{SERVER_KEY}"}
    response = requests.get(f"{BASE_URL}/server/commandlogs", headers=headers)

    print("Raw API Response:", response.status_code,
          response.text)  # Debugging

    if response.status_code == 200:
        data = response.json()

        if isinstance(data, list) and data:  # Ensure it's a non-empty list
            log_messages = []
            for log in data:
                # Extract and clean command and user (without timestamp)
                command = log.get("Command", "N/A")  # Use 'Command' key
                player_raw = log.get(
                    "Player",
                    "Unknown")  # Use 'Player' key (contains both name and ID)
                user = player_raw.split(":")[
                    0]  # Extract player name by splitting at ":"

                # Format the command log entry without the timestamp
                log_messages.append(
                    f"**Command:** {command} | **User:** {user}")

            embed = discord.Embed(title="Command Logs",
                                  description="\n".join(log_messages),
                                  color=discord.Color.blue())
            await ctx.send(embed=embed)
        else:
            await ctx.send("No command logs available.")
    else:
        await ctx.send(f"Failed to fetch command logs: {response.text}")


@bot.command(aliases=['mod', 'mc', 'mlogs'])
@is_hr()
async def moderator_calls(ctx):
    """Fetches and sends the moderator call logs."""
    headers = {"Server-Key": f"{SERVER_KEY}"}
    response = requests.get(f"{BASE_URL}/server/modcalls", headers=headers)

    print("Raw API Response:", response.status_code,
          response.text)  # Debugging

    if response.status_code == 200:
        data = response.json()

        if isinstance(data, list) and data:  # Ensure it's a non-empty list
            mod_messages = []
            for call in data:
                # Extract and clean player names (removing user IDs)
                caller_raw = call.get("Caller", "Unknown")
                moderator_raw = call.get("Moderator", "Unknown")

                caller = caller_raw.split(
                    ":")[0] if ":" in caller_raw else caller_raw
                moderator = moderator_raw.split(
                    ":")[0] if ":" in moderator_raw else moderator_raw

                timestamp = call.get("Timestamp", "Unknown Time")

                # Format the moderator call log
                mod_messages.append(
                    f"**Caller:** {caller} | **Moderator:** {moderator} | **Time:** {timestamp}"
                )

            embed = discord.Embed(title="Moderator Calls",
                                  description="\n".join(mod_messages),
                                  color=discord.Color.blue())
            await ctx.send(embed=embed)
        else:
            await ctx.send("No moderator calls available.")
    else:
        await ctx.send(f"Failed to fetch moderator call logs: {response.text}")


@bot.command(aliases=['bp', 'bl'])
@is_hr()
async def banned_players(ctx):
    """Fetches and sends a list of banned players."""
    headers = {"Server-Key": f"{SERVER_KEY}"}
    response = requests.get(f"{BASE_URL}/server/bans", headers=headers)

    if response.status_code == 200:
        data = response.json()

        # Debug: Print the API response to check the structure
        print("Raw API Response:", data)

        if isinstance(data,
                      dict) and data:  # Check if it's a non-empty dictionary
            ban_list = []
            for player_id, player_name in data.items():
                # Format the banned player's info
                ban_list.append(
                    f"**Player:** {player_name} | **ID:** {player_id}")

            embed = discord.Embed(title="Banned Players",
                                  description="\n".join(ban_list),
                                  color=discord.Color.red())
            await ctx.send(embed=embed)
        else:
            await ctx.send("No banned players.")
    else:
        await ctx.send(f"Failed to fetch banned players: {response.text}")


@bot.command(aliases=['vehicles', 'sv', 'spv'])
@is_hr()
async def spawned_vehicles(ctx):
    """Fetches and sends a list of spawned vehicles in the server."""
    headers = {"Server-Key": f"{SERVER_KEY}"}
    response = requests.get(f"{BASE_URL}/server/vehicles", headers=headers)

    if response.status_code == 200:
        data = response.json()

        # Debug: Print the API response to check the structure
        print("Raw API Response:", data)

        if isinstance(data, list) and data:  # Ensure it's a non-empty list
            vehicle_list = []
            for vehicle in data:
                # Extract Vehicle Name, Owner, and Texture
                name = vehicle.get("Name", "Unknown")
                owner = vehicle.get("Owner", "Unknown")
                texture = vehicle.get("Texture", "Default")

                # Format vehicle information
                vehicle_list.append(
                    f"**Vehicle:** {name} | **Owner:** {owner} | **Texture:** {texture}"
                )

            embed = discord.Embed(title="Spawned Vehicles",
                                  description="\n".join(vehicle_list),
                                  color=discord.Color.blue())
            await ctx.send(embed=embed)
        else:
            await ctx.send("No vehicles currently spawned.")
    else:
        await ctx.send(f"Failed to fetch spawned vehicles: {response.text}")


PRIORITY_CODES = [
    "10-37", "10-40", "10-27"
    # Add more codes as needed
]


@bot.command()
async def priority(ctx, code: str, *, location: str):
    """Command to send a priority alert with an embed and ping roles."""

    # Check if the author has the dispatcher role
    if DISPATCH_ROLE_ID not in [role.id for role in ctx.author.roles]:
        await ctx.send(
            "🚫 You don't have the required dispatcher role to use this command."
        )
        return

    # Check if the provided code is in the list of valid priority codes
    if code not in PRIORITY_CODES:
        await ctx.send(
            f"🚫 Invalid code. Please use a valid priority code (e.g., {', '.join(PRIORITY_CODES[:5])}...)."
        )
        return

    try:
        # Get role mentions
        dispatch_role = f"<@&{DISPATCH_ROLE_ID}>"
        police_role = f"<@&{POLICE_ROLE_ID}>"
        state_police_role = f"<@&{STATE_POLICE_ROLE_ID}>"
        sheriff_role = f"<@&{SHERIFF_ROLE_ID}>"
        # Create the embed
        embed = discord.Embed(
            title="🚨 **Priority** 🚨",
            description=
            f"We have a {code} in progress at {location} all units respond! Please remain RTO at **ALL** times! Please follow all **LEO HANDBOOKS** to do this properly!",
            color=discord.Color.red())
        embed.set_footer(
            text=f"Reported by {ctx.author.name}",
            icon_url=ctx.author.avatar.url if ctx.author.avatar else None)

        # Send the message with role pings
        alert_message = f"{dispatch_role} {police_role} {state_police_role} {sheriff_role}"
        await ctx.send(alert_message, embed=embed)
    except Exception as e:
        await ctx.send(f"An error occurred: {str(e)}")


@bot.command()
@is_hr()
async def help(ctx, *args):
    """Displays a help message with available bot commands."""

    # If the user asks for help on a specific command or category
    if args:
        command_or_category = args[0].lower()

        if command_or_category == "ssu":
            embed = discord.Embed(
                title="!SSU - Start Server",
                description=
                "Starts up the ER:LC server and sends a notification.",
                color=discord.Color.green())
            embed.add_field(name="Usage", value="!SSU", inline=False)
            embed.add_field(
                name="Description",
                value="This command starts the ER:LC private server.",
                inline=False)
            embed.add_field(name="Aliases", value="!SSU, !ssu", inline=False)
            await ctx.send(embed=embed)

        elif command_or_category == "ssd":
            embed = discord.Embed(
                title="!SSD - Shutdown Server",
                description=
                "Shuts down the ER:LC private server and starts peace and priority timers.",
                color=discord.Color.red())
            embed.add_field(name="Usage", value="!SSD", inline=False)
            embed.add_field(name="Description",
                            value="This command shuts down the server.",
                            inline=False)
            embed.add_field(name="Aliases", value="!SSD, !ssd", inline=False)
            await ctx.send(embed=embed)

        elif command_or_category == "banned_players":
            embed = discord.Embed(
                title="!banned_players - Banned Players",
                description="Fetches and sends a list of banned players.",
                color=discord.Color.blue())
            embed.add_field(name="Usage",
                            value="!banned_players",
                            inline=False)
            embed.add_field(
                name="Description",
                value="This command fetches the list of banned players.",
                inline=False)
            embed.add_field(name="Aliases",
                            value="!banned_players, !bp, !bl",
                            inline=False)
            await ctx.send(embed=embed)

        elif command_or_category == "server":
            embed = discord.Embed(
                title="!ss - Server Status",
                description="Fetches and sends the server status.",
                color=discord.Color.purple())
            embed.add_field(name="Usage", value="!ss", inline=False)
            embed.add_field(
                name="Description",
                value=
                "This command fetches and shows the current server status.",
                inline=False)
            embed.add_field(name="Aliases", value="!ss, !ssu", inline=False)
            await ctx.send(embed=embed)

        # Add more commands and categories as needed

        else:
            await ctx.send(
                f"Sorry, I couldn't find any command or category named {command_or_category}."
            )

    else:
        # Default help message showing all commands in categories
        embed = discord.Embed(
            title="Help - ASRP Bot Commands",
            description="Here are the available categories and commands:",
            color=discord.Color.blue())

        embed.add_field(name="Server Commands",
                        value="!ss, !ssu, !ssd",
                        inline=False)
        embed.add_field(name="Player Commands",
                        value="!pis, !banned_players, !players_in_queue",
                        inline=False)
        embed.add_field(
            name="Log Commands",
            value="!join_logs, !kill_logs, !command_logs, !moderator_calls",
            inline=False)
        embed.add_field(name="Vehicle Commands",
                        value="!spawned_vehicles",
                        inline=False)

        # Add aliases section
        embed.add_field(
            name="Aliases",
            value=
            "**Players In Server**: !pis, !ps, !pl, **Banned Players**: !banned_players, !bp, !bl, **Spawned Vehicles**: !spawned_vehicles, !vehicles, !sv, !spv, **Mod Calls**: !moderator_calls, !mod, !mlogs, !mc, **Command Logs**: !command_logs, !cmdlogs, !cl",
            inline=False)

        embed.set_footer(
            text="Type !help <command> for more info on a specific command.")

        await ctx.send(embed=embed)

codes = {}
with open("codes.txt", "r") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            code_number, description = line.split(" ", 1)
            codes[code_number] = description
        except ValueError:
            print(f"Skipping invalid line: {line}")
print("Loaded codes:", codes)

# ---- UNIT TABLE ----
units = {}  # key: callsign, value: dict with status info

@bot.command()
@is_hr()  # your existing HR check
async def join(ctx):
    """Forces the bot to join the VC you're in."""
    if ctx.author.voice:  # make sure user is in a VC
        channel = ctx.author.voice.channel
        if ctx.voice_client:  # already connected somewhere
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        await ctx.send(f"✅ Joined {channel.name}")
    else:
        await ctx.send("❌ You must be in a VC for me to join.")

def init_unit(callsign):
    if callsign not in units:
        units[callsign] = {
            "Status": "10-8",           # default available
            "Current_Call": None,       # call they originated
            "Attached_To_Call": None,   # assisting
            "Locked_Until_10_8": False # prevents multi-assign
        }

# ---- HELPER FUNCTIONS ----
def extract_codes_from_message(message_text):
    found_codes = re.findall(r"10-\d{1,2}", message_text)
    return [code for code in found_codes if code in codes]

async def send_dispatch_tts(message_text):
    mp3_file = "dispatch.mp3"
    
    # Generate TTS with Edge
    communicate = edge_tts.Communicate(message_text, voice="en-US-AriaNeural")
    await communicate.save(mp3_file)
    
    # Play in the Police RTO VC
    for vc in bot.voice_clients:
        if vc.channel.id == RTO_CHANNEL_ID:
            if vc.is_playing():
                vc.stop()
            vc.play(FFmpegPCMAudio(mp3_file, executable=FFMPEG_BINARY))
            print(f"[TTS] Playing in {vc.channel.name}")
async def ensure_police_rto():
    if SSD_ACTIVE:
        return  # don't join during SSD
    
    for guild in bot.guilds:
        police_channel = guild.get_channel(RTO_CHANNEL_ID)
        if police_channel and not any(vc.channel.id == RTO_CHANNEL_ID for vc in bot.voice_clients):
            await police_channel.connect()

# ---- DISPATCH LOGIC ----
async def process_voice_command(speaker_callsign, message_text):
    init_unit(speaker_callsign)
    if "dispatch" not in message_text.lower():
        return

    message_text = message_text.lower()

    if "show me on" in message_text:
        await handle_dispatch_request(speaker_callsign, message_text)
    elif "attach me to" in message_text:
        await handle_attach_request(speaker_callsign, message_text)
    elif "10-8" in message_text:
        await handle_10_8(speaker_callsign)

async def handle_dispatch_request(speaker_callsign, message_text):
    requested_codes = extract_codes_from_message(message_text)
    if not requested_codes:
        await send_dispatch_tts(f"{speaker_callsign}, no valid codes detected.")
        return

    # Filter available units (10-8, not attached, not locked)
    available_units = [cs for cs, u in units.items() 
                       if u["Status"]=="10-8" and not u["Attached_To_Call"] and not u["Locked_Until_10_8"]]
    if not available_units:
        await send_dispatch_tts(f"No available units for request from {speaker_callsign}")
        return

    assigned_unit = available_units[0]
    units[assigned_unit]["Attached_To_Call"] = f"Call by {speaker_callsign}"
    units[assigned_unit]["Locked_Until_10_8"] = True

    codes_text = ", ".join([f"{c} ({codes[c]})" for c in requested_codes])
    await send_dispatch_tts(f"10-4, {assigned_unit} respond to {codes_text}")

async def handle_attach_request(speaker_callsign, message_text):
    init_unit(speaker_callsign)
    # attach to last active call
    active_calls = [u["Current_Call"] for u in units.values() if u["Current_Call"]]
    if not active_calls:
        await send_dispatch_tts(f"{speaker_callsign}, no active calls to attach to.")
        return
    call_to_attach = active_calls[-1]
    units[speaker_callsign]["Attached_To_Call"] = call_to_attach
    units[speaker_callsign]["Locked_Until_10_8"] = True
    await send_dispatch_tts(f"{speaker_callsign} attached to call {call_to_attach}.")

async def handle_10_8(speaker_callsign):
    init_unit(speaker_callsign)
    units[speaker_callsign]["Status"] = "10-8"
    units[speaker_callsign]["Current_Call"] = None
    units[speaker_callsign]["Attached_To_Call"] = None
    units[speaker_callsign]["Locked_Until_10_8"] = False
    await send_dispatch_tts(f"{speaker_callsign} is now 10-8 and available.")

@bot.command()
async def tts_test(ctx, *, text):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        if ctx.voice_client:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        await send_dispatch_tts(text)
        await ctx.send("✅ TTS played!")
    else:
        await ctx.send("❌ You must be in a VC to test TTS.")from llama_cpp import Llama

llm = Llama(model_path="mpt-7b-instruct.ggmlv3.q4_0.bin")

async def ai_dispatch_response(callsign, message_text):
    prompt = f"""
You are a police dispatcher AI. Respond naturally to the officer {callsign}.
Interpret any 10-codes mentioned in the message and respond as a dispatcher would.
Message: {message_text}
"""
    response = llm(prompt=prompt, max_tokens=150)
    return response["choices"][0]["text"]

async def ai_dispatch_tts(callsign, message_text):
    ai_text = await ai_dispatch_response(callsign, message_text)
    await send_dispatch_tts(ai_text)

# ---------------- DISPATCH LOGIC ----------------
async def process_voice_command(speaker_callsign, message_text):
    init_unit(speaker_callsign)
    if "dispatch" not in message_text.lower():
        return
    await ai_dispatch_tts(speaker_callsign, message_text)

if __name__ == '__main__':
    keep_alive()
    bot.run(TOKEN)
