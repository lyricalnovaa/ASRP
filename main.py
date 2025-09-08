import os
import discord
from discord.ext import commands
import requests
from keep_alive import keep_alive
import json
import datetime
import asyncio
from discord import FFmpegPCMAudio
import re
import tarfile
import shutil
import edge_tts
import speech_recognition as sr
import io
import numpy as np
import threading
import time

RTO_CHANNEL_ID = 1341573057952878674
# Load secrets from environment variables
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ERLC_API_KEY = os.getenv("ERLC_API_KEY")
SERVER_KEY = os.getenv("SERVER_KEY")
SSD_ACTIVE = False

FFMPEG_DIR = os.path.join(os.getcwd(), "ffmpeg")
FFMPEG_BINARY = os.path.join(FFMPEG_DIR, "ffmpeg")
FFMPEG_URL = "https://drive.google.com/uc?export=download&id=1fBGqmBBi48V1gQwGIXs05SJA-LVjGDBu"

# Dictionary to hold the state of each unit (user)
UNITS = {}

# Dictionary to hold voice channel objects to manage voice connections
VOICE_CLIENTS = {}

# Use a lock to ensure thread-safe access to the UNITS dictionary
UNITS_LOCK = threading.Lock()

# Define intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True
intents.guilds = True

# Initialize the bot
bot = commands.Bot(command_prefix="!", intents=intents)

# Check for FFmpeg binary and download if it doesn't exist
def ensure_ffmpeg():
    if os.path.exists(FFMPEG_BINARY):
        return FFMPEG_BINARY

    os.makedirs(FFMPEG_DIR, exist_ok=True)

    print("Downloading FFmpeg binary from Google Drive...")
    try:
        r = requests.get(FFMPEG_URL, stream=True)
        r.raise_for_status()
        with open(os.path.join(FFMPEG_DIR, "ffmpeg.tar.gz"), "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print("Download complete. Extracting...")
        with tarfile.open(os.path.join(FFMPEG_DIR, "ffmpeg.tar.gz"), "r:gz") as tar:
            tar.extractall(path=FFMPEG_DIR)
        os.remove(os.path.join(FFMPEG_DIR, "ffmpeg.tar.gz"))
        print("Extraction complete. FFmpeg is ready.")
        return FFMPEG_BINARY
    except Exception as e:
        print(f"Failed to download or extract FFmpeg: {e}")
        return None

# Global variable to hold the FFmpeg binary path
FFMPEG_PATH = ensure_ffmpeg()

# Pre-defined dispatch responses for common codes
DISPATCH_RESPONSES = {
    "10-4": "Roger that, understood.",
    "10-7": "Unit 10-7. Dispatched to standby.",
    "10-8": "Unit 10-8, in service, clear.",
    "10-20": "Please provide your location.",
    "10-23": "Unit 10-23, standby.",
    "10-99": "Unit 10-99, officer in distress. Requesting immediate assistance.",
    "10-100": "Unit 10-100, requesting immediate backup.",
    "standby": "Copy, standby.",
    "in service": "Copy, in service.",
    "show me available": "Roger, you are shown as available.",
    "show me unavailable": "Roger, you are shown as unavailable.",
    "show me in route": "Roger, you are shown as in route.",
    "show me on scene": "Roger, you are shown as on scene.",
}

def get_dispatch_response(callsign, message_text):
    """
    Generate a simple, rule-based dispatch response based on keywords.
    """
    for code, response in DISPATCH_RESPONSES.items():
        if code in message_text.lower():
            # If the code is found, use a pre-defined response
            return f"{callsign}, {response}"
    
    # If no specific code is found, provide a generic response
    return f"{callsign}, received. Please state your code."

# Text-to-speech function using edge-tts
async def send_dispatch_tts(text):
    if not text:
        return
    
    try:
        voice = 'en-US-JennyNeural'
        communicate = edge_tts.Communicate(text, voice)
        tts_file = "dispatch_tts.mp3"
        await communicate.save(tts_file)
        
        voice_client = VOICE_CLIENTS.get(RTO_CHANNEL_ID)
        if voice_client and voice_client.is_connected():
            if voice_client.is_playing():
                voice_client.stop()
            
            source = FFmpegPCMAudio(tts_file, executable=FFMPEG_PATH)
            voice_client.play(source)
            
            while voice_client.is_playing():
                await asyncio.sleep(1)
            
            os.remove(tts_file)
    except Exception as e:
        print(f"Error in TTS or audio playback: {e}")

async def rule_based_dispatch_tts(callsign, message_text):
    response_text = get_dispatch_response(callsign, message_text)
    await send_dispatch_tts(response_text)

# ---------------- DISPATCH LOGIC ----------------
def get_callsign(member):
    """
    Generate callsign from the first 5 characters of the member's display name.
    """
    return member.display_name[:5].upper()

def init_unit(member):
    """
    Initializes a unit for a member if one doesn't exist.
    """
    user_id = member.id
    with UNITS_LOCK:
        if user_id not in UNITS:
            callsign = get_callsign(member)
            UNITS[user_id] = {
                "callsign": callsign,
                "user": member,
                "status": "Available",
                "timestamp": datetime.datetime.utcnow().isoformat()
            }
            print(f"Initialized new unit for {member.display_name} with callsign: {callsign}")
            return UNITS[user_id]
        return UNITS[user_id]

async def process_voice_command(member, message_text):
    """
    Processes a transcribed voice command.
    """
    unit_info = init_unit(member)
    callsign = unit_info["callsign"]

    if "dispatch" in message_text.lower():
        command_text = message_text.lower().split("dispatch", 1)[-1].strip()
        print(f"Command detected from {callsign}: '{command_text}'")
        await rule_based_dispatch_tts(callsign, command_text)

def transcribe_audio_from_bytes(audio_bytes, sample_rate, sample_width):
    """
    Transcribes raw audio bytes using the Google Speech Recognition API.
    """
    try:
        r = sr.Recognizer()
        audio_data = sr.AudioData(audio_bytes, sample_rate, sample_width)
        print("Transcribing audio...")
        text = r.recognize_google(audio_data)
        print(f"Transcription result: {text}")
        return text
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        print(f"Could not request results from Google Speech Recognition service; {e}")
        return ""

async def voice_listener(voice_client):
    """
    Listens to audio from a voice channel and transcribes it.
    """
    
    while voice_client.is_connected():
        try:
            print("Listening for 3 seconds...")
            audio_data = await asyncio.wait_for(voice_client.listen(timeout=3.0), timeout=3.5)
            
            pcm_data = audio_data.get_converted_audio()
            
            member = audio_data.member
            if not member:
                continue

            text = await asyncio.to_thread(
                transcribe_audio_from_bytes,
                pcm_data.getvalue(),
                pcm_data.rate,
                pcm_data.sample_width
            )

            if text:
                print(f"Transcribed '{text}' from {member.display_name}")
                await process_voice_command(member, text)

        except asyncio.TimeoutError:
            pass
        except Exception as e:
            print(f"An error occurred during voice transcription: {e}")
            break

@bot.event
async def on_ready():
    print(f"Bot is ready and logged in as {bot.user}")
    
    # Automatically join the RTO channel
    try:
        channel = bot.get_channel(RTO_CHANNEL_ID)
        if channel and isinstance(channel, discord.VoiceChannel):
            if channel.guild.voice_client:
                print(f"Already connected to {channel.name}.")
                voice_client = channel.guild.voice_client
            else:
                print(f"Attempting to join RTO channel: {channel.name}")
                voice_client = await channel.connect()
            
            VOICE_CLIENTS[RTO_CHANNEL_ID] = voice_client
            
            bot.loop.create_task(voice_listener(voice_client))
        else:
            print(f"RTO channel with ID {RTO_CHANNEL_ID} not found or is not a voice channel.")
    except Exception as e:
        print(f"An error occurred while trying to auto-join the RTO channel: {e}")

@bot.command()
async def join(ctx):
    """
    Joins the user's current voice channel.
    """
    if ctx.author.voice and ctx.author.voice.channel:
        channel = ctx.author.voice.channel
        try:
            voice_client = await channel.connect()
            VOICE_CLIENTS[channel.id] = voice_client
            await ctx.send(f"Joined {channel.name}!")
            bot.loop.create_task(voice_listener(voice_client))
        except discord.ClientException:
            await ctx.send("I'm already in a voice channel.")
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
    else:
        await ctx.send("You are not in a voice channel.")
if __name__ == '__main__':
    keep_alive()
    bot.run(TOKEN)
