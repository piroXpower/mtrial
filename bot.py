import asyncio
import os
from pyrogram import Client, filters
from pyrogram.types import Message
# WARNING: Using py-tgcalls==0.6.0. This version is deprecated and unstable.
from pytgcalls import PyTgCalls
from pytgcalls.types import Update
from pytgcalls.types.input_stream import InputStream, InputFileType
from pytgcalls.types.exceptions import GroupCallNotFound, NotInGroupCallError, NoActiveGroupCall

# ====================================================================
# 1. CONFIGURATION (REPLACE WITH YOUR OWN VALUES)
# ====================================================================
API_ID = 33090746 # <--- REPLACE THIS
API_HASH = "b8ebbe19e5c5e0fd4f0089ab4553f959" # <--- REPLACE THIS
SESSION_NAME = ""

# ====================================================================
# 2. GLOBAL STATE AND CLIENT INITIALIZATION
# ====================================================================

app = Client(SESSION_NAME, API_ID, API_HASH)
# Initialize PyTgCalls with the Pyrogram client
voice_client = PyTgCalls(app) 

QUEUE = []
CURRENT_PLAYING = None
IS_PAUSED = False

# ====================================================================
# 3. UTILITY FUNCTION (Track Playback Logic - Adapted for v0.6.0)
# ====================================================================

async def play_next_track(client: Client):
    """Plays the next track in the queue or leaves the VC if the queue is empty."""
    global CURRENT_PLAYING
    
    if not QUEUE:
        if CURRENT_PLAYING:
            try:
                # v0.6.0 uses 'leave_call'
                await voice_client.leave_call(CURRENT_PLAYING["chat_id"])
            except Exception:
                pass 
        CURRENT_PLAYING = None
        return

    track = QUEUE.pop(0) 
    chat_id = track["chat_id"]
    file_path = track["file_path"]
    
    try:
        # v0.6.0 uses InputStream and InputFileType.
        input_stream = InputStream(
            file_path,
            InputFileType.MusicStream # Use MusicStream for general audio files
        )
        # v0.6.0 uses 'start_stream'
        await voice_client.start_stream(chat_id, input_stream)
        
        CURRENT_PLAYING = track
        await client.send_message(chat_id, f"🎧 Now Playing: `{os.path.basename(file_path)}`")
    except Exception as e:
        print(f"Error playing track: {e}")
        # Try playing the next one if this one fails
        await play_next_track(client) 

# ====================================================================
# 4. PYTGCALLS EVENT HANDLER (Adapted for v0.6.0)
# ====================================================================

@voice_client.on_update()
async def update_handler(client: PyTgCalls, update: Update):
    """Handles all updates, including stream end."""
    # Check if the update is a stream end event
    if update.name == 'on_stream_end' and CURRENT_PLAYING:
        print(f"Stream ended for chat {update.chat_id}. Playing next...")
        await play_next_track(app)


# ====================================================================
# 5. PYROGRAM COMMAND HANDLERS
# ====================================================================

@app.on_message(filters.me & filters.command("stream", prefixes="."))
async def stream_audio_command(client: Client, message: Message):
    """Command: .stream - Streams the replied-to audio file."""
    global CURRENT_PLAYING

    if not message.reply_to_message or not message.reply_to_message.audio:
        await message.edit("❌ Reply to an **audio file** to stream it.")
        return

    m = await message.edit("📥 Downloading and preparing audio...")
    
    try:
        # Download media is standard Pyrogram v2.x.x method
        file_path = await client.download_media(message.reply_to_message)
    except Exception as e:
        await m.edit(f"❌ Download failed: `{e}`")
        return
        
    chat_id = message.chat.id
    new_track = {"chat_id": chat_id, "file_path": file_path}

    if CURRENT_PLAYING:
        QUEUE.append(new_track)
        await m.edit(f"✅ Added to queue. Position: **{len(QUEUE)}**")
        return
    
    try:
        # v0.6.0 uses 'join_call'
        await voice_client.join_call(chat_id) 
    except NoActiveGroupCall:
        await m.edit("❌ No active voice chat found in this group.")
        os.remove(file_path) 
        return
    except Exception as e:
        # Catch other errors, like already joined or permission errors
        if "already joined" not in str(e).lower():
             await m.edit(f"❌ Error joining VC: {e}")
             os.remove(file_path)
             return

    # Start the stream 
    await play_next_track(client)
    await m.edit("▶️ Streaming started!")


@app.on_message(filters.me & filters.command("queue", prefixes="."))
async def show_queue_command(client, message):
    """Command: .queue - Shows the current queue."""
    if not QUEUE:
        await message.edit("The queue is currently **empty**.")
        return
    
    text = "🎧 **Current Queue:**\n"
    for i, track in enumerate(QUEUE):
        text += f"**{i+1}.** `{os.path.basename(track['file_path'])}`\n"
        
    await message.edit(text)

@app.on_message(filters.me & filters.command("skip", prefixes="."))
async def skip_track_command(client, message):
    """Command: .skip - Skips the current track."""
    if not CURRENT_PLAYING:
        await message.edit("Nothing is currently playing.")
        return
        
    await message.edit("⏩ Skipping current track...")
    try:
        # v0.6.0 uses 'stop_stream'
        await voice_client.stop_stream(CURRENT_PLAYING["chat_id"]) 
        # The update handler will call play_next_track()
        await message.edit("✅ Track **skipped**.")
    except Exception as e:
        await message.edit(f"❌ Failed to skip: {e}")

    
@app.on_message(filters.me & filters.command("pause", prefixes="."))
async def pause_stream_command(client, message):
    """Command: .pause - Pauses the stream."""
    global IS_PAUSED
    if not CURRENT_PLAYING or IS_PAUSED:
        await message.edit("Nothing is playing or already paused.")
        return
    
    # v0.6.0 uses 'pause_stream'
    await voice_client.pause_stream(CURRENT_PLAYING["chat_id"])
    IS_PAUSED = True
    await message.edit("⏸️ Stream **paused**.")

@app.on_message(filters.me & filters.command("play", prefixes="."))
async def resume_stream_command(client, message):
    """Command: .play - Resumes the stream."""
    global IS_PAUSED
    if not CURRENT_PLAYING or not IS_PAUSED:
        await message.edit("Nothing is paused to resume.")
        return
        
    # v0.6.0 uses 'resume_stream'
    await voice_client.resume_stream(CURRENT_PLAYING["chat_id"])
    IS_PAUSED = False
    await message.edit("▶️ Stream **resumed**.")
    
@app.on_message(filters.me & filters.command("stop", prefixes="."))
async def stop_stream_command(client, message):
    """Command: .stop - Stops all playback and leaves VC."""
    global QUEUE, CURRENT_PLAYING, IS_PAUSED
    
    if not CURRENT_PLAYING:
        await message.edit("Nothing is currently playing.")
        return

    chat_id = CURRENT_PLAYING["chat_id"]

    try:
        # v0.6.0 uses 'leave_call'
        await voice_client.leave_call(chat_id)
    except Exception:
        pass 

    QUEUE.clear()
    CURRENT_PLAYING = None
    IS_PAUSED = False
    
    await message.edit("⏹️ Playback **stopped** and voice chat left.")

# ====================================================================
# 6. MAIN EXECUTION
# ====================================================================

async def main():
    if API_ID == 1234567 or API_HASH == "0123456789abcdef0123456789abcdef":
        print("!!! ERROR: Please replace API_ID and API_HASH with your own. !!!")
        return
        
    print("Starting client...")
    await app.start() 
    print("Pyrogram client started. Initializing voice client...")
    # v0.6.0 uses 'start'
    await voice_client.start() 
    print("Userbot is fully ready! Use .stream in a group with an active VC.")
    
    await asyncio.Future() 

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down userbot.")
        # Clean up clients upon exit
        if app.is_connected:
            asyncio.run(app.stop())
        if voice_client.is_connected:
            asyncio.run(voice_client.stop())

