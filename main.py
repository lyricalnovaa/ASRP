import os
import discord
from discord.ext import commands, tasks
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
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
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
# The key is the user's Discord ID, and the value is a dictionary
# containing their current state (e.g., callsign, status).
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

# Initialize TTS and AI models
try:
    print("Loading AI model...")
    MODEL_NAME = "microsoft/DialoGPT-medium"
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)
    print("AI model loaded successfully.")
except Exception as e:
    print(f"Error loading AI model: {e}")
    tokenizer = None
    model = None

def generate_dispatch_response(callsign, message_text, max_tokens=150):
    """
    Generate a dispatch-style AI response using Transformers
    """
    if not tokenizer or not model:
        return "AI model is not available. Please check the logs."
    
    prompt = f"You are a police dispatcher AI. Respond naturally to officer {callsign}. Interpret any 10-codes mentioned in the message and respond as a dispatcher would.\nMessage: {message_text}\nDispatcher:"
    inputs = tokenizer(prompt, return_tensors="pt")
    
    # Generate output
    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=max_tokens)
    
    response_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
    # Optionally strip the prompt from response
    response_text = response_text.replace(prompt, "").strip()
    return response_text

# Async wrapper for the AI model
async def ai_dispatch_response(callsign, message_text):
    return generate_dispatch_response(callsign, message_text)

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

async def ai_dispatch_tts(callsign, message_text):
    ai_text = await ai_dispatch_response(callsign, message_text)
    await send_dispatch_tts(ai_text)

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
        await ai_dispatch_tts(callsign, command_text)

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
        # This is expected when there's no speech, so we don't need a noisy printout
        # print("Google Speech Recognition could not understand audio")
        return ""
    except sr.RequestError as e:
        print(f"Could not request results from Google Speech Recognition service; {e}")
        return ""

async def voice_listener(voice_client):
    """
    Listens to audio from a voice channel and transcribes it.
    """
    
    # This loop continuously listens for voice
    while voice_client.is_connected():
        try:
            # The bot listens for a 3-second segment of audio
            print("Listening for 3 seconds...")
            audio_data = await asyncio.wait_for(voice_client.listen(timeout=3.0), timeout=3.5)
            
            # Convert Opus-encoded data to PCM
            pcm_data = audio_data.get_converted_audio()
            
            # Find the member who spoke
            member = audio_data.member
            if not member:
                continue

            # Transcribe the audio
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
            # This is normal; it just means no one spoke in the 3 seconds
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
            
            # Store the voice client
            VOICE_CLIENTS[RTO_CHANNEL_ID] = voice_client
            
            # Start the voice listener
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
