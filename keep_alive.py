from flask import Flask
import threading
import time
import requests
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is online!"

def run():
    while True:
        try:
            app.run(host="0.0.0.0", port=8080)
        except Exception as e:
            print(f"Server crashed: {e}")
            time.sleep(4)  # Wait before restarting

def keep_alive():
    thread = threading.Thread(target=run, daemon=True)
    thread.start()

keep_alive()