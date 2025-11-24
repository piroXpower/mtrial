import asyncio
import os
from pyrogram import Client, filters
from pyrogram.types import Message
from pytgcalls import PyTgCalls, StreamType
from pytgcalls.types import AudioPiped
from pytgcalls.exceptions import AlreadyJoinedError, NoActiveGroupCall

# ====================================================================
# 1. CONFIGURATION (REPLACE WITH YOUR OWN VALUES)
# ====================================================================

# Get these from https://my.telegram.org/
API_ID = 33090746 # <--- REPLACE THIS
API_HASH = "b8ebbe19e5c5e0fd4f0089ab4553f959" # <--- REPLACE THIS
SESSION_NAME = ""

# ====================================================================
# 2. GLOBAL STATE AND CLIENT INITIALIZATION
# ====================================================================

# Initialize Pyrogram Client (Userbot)
app = Client(SESSION_NAME, API_ID, API_HASH)
# Initialize PyTgCalls with the Pyrogram client
voice_client = PyTgCalls(app) 

# State variables
QUEUE = []
CURRENT_PLAYING = None
IS_PAUSED = False

# ====================================================================
# 3. UTILITY FUNCTION (Track Playback Logic)
# ====================================================================

async def play_next_track(client: Client):
    """Plays the next track in the queue or leaves the VC if the queue is empty."""
    global CURRENT_PLAYING
    
    if not QUEUE:
        print("Queue empty, leaving voice chat.")
        if CURRENT_PLAYING:
            try:
                await voice_client.leave_group_call(CURRENT_PLAYING["chat_id"])
            except Exception:
                pass # Already left or error
        CURRENT_PLAYING = None
        return

    # Pop the next track from the queue (FIFO)
    track = QUEUE.pop(0) 
    chat_id = track["chat_id"]
    file_path = track["file_path"]
    
    try:
        # Stream the audio. AudioPiped is used for raw audio streams.
        await voice_client.stream_audio(
            chat_id, 
            AudioPiped(file_path),
            stream_type=StreamType().pulse_stream
        )
        CURRENT_PLAYING = track
        # Notify the user or log the start
        await client.send_message(chat_id, f"🎧 Now Playing: `{os.path.basename(file_path)}`")
    except Exception as e:
        print(f"Error playing track: {e}")
        # Try playing the next one if this one fails
        await play_next_track(client) 

# ====================================================================
# 4. PYTGCALLS EVENT HANDLER
# ====================================================================

@voice_client.on_stream_end()
async def stream_end_handler(client, update):
    """Automatically called when the current track finishes."""
    await play_next_track(client)

# ====================================================================
# 5. PYROGRAM COMMAND HANDLERS
# ====================================================================

@app.on_message(filters.me & filters.command("play", prefixes="."))
async def stream_audio_command(client: Client, message: Message):
    """Command: .stream - Streams the replied-to audio file."""
    global CURRENT_PLAYING

    if not message.reply_to_message or not message.reply_to_message.audio:
        await message.edit("❌ Reply to an **audio file** to stream it.")
        return

    m = await message.edit("📥 Downloading and preparing audio...")
    
    # 1. Download the audio file
    try:
        # Pyrogram handles the download and temporary storage
        file_path = await client.download_media(message.reply_to_message)
    except Exception as e:
        await m.edit(f"❌ Download failed: `{e}`")
        return
        
    chat_id = message.chat.id
    new_track = {"chat_id": chat_id, "file_path": file_path}

    # 2. Check if anything is currently playing
    if CURRENT_PLAYING:
        # Add to queue
        QUEUE.append(new_track)
        await m.edit(f"✅ Added to queue. Position: **{len(QUEUE)}**")
        return
    
    # 3. Start playing if nothing is playing
    try:
        # Join the voice chat if not already joined
        await voice_client.join_group_call(chat_id, StreamType().pulse_stream) 
    except NoActiveGroupCall:
        await m.edit("❌ No active voice chat found in this group.")
        # Clean up the downloaded file
        os.remove(file_path) 
        return
    except AlreadyJoinedError:
        pass # Already in VC, proceed to stream

    # Start the stream by calling the utility function
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
        # Use only the filename for a clean display
        text += f"**{i+1}.** `{os.path.basename(track['file_path'])}`\n"
        
    await message.edit(text)

@app.on_message(filters.me & filters.command("skip", prefixes="."))
async def skip_track_command(client, message):
    """Command: .skip - Skips the current track."""
    if not CURRENT_PLAYING:
        await message.edit("Nothing is currently playing.")
        return
        
    await message.edit("⏩ Skipping current track...")
    # Stop the current stream to trigger the stream_end_handler
    try:
        await voice_client.end_stream(CURRENT_PLAYING["chat_id"]) 
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

    # 1. Leave VC
    try:
        await voice_client.leave_group_call(chat_id)
    except Exception:
        pass # Already left or error

    # 2. Clear state
    QUEUE.clear()
    CURRENT_PLAYING = None
    IS_PAUSED = False
    
    await message.edit("⏹️ Playback **stopped** and voice chat left.")

# ====================================================================
# 6. MAIN EXECUTION
# ====================================================================

async def main():
    """Starts both Pyrogram and PyTgCalls clients."""
    print("Starting client...")
    
    # Start Pyrogram client
    await app.start() 
    print("Pyrogram client started. Initializing voice client...")
    
    # Start PyTgCalls client (must start after Pyrogram)
    await voice_client.start() 
    print("Userbot is fully ready! Use .stream in a group with an active VC.")
    
    # Keep the client running indefinitely
    await asyncio.Future() 

if __name__ == "__main__":
    # Ensure API credentials are not the placeholders
    if API_ID == 1234567 or API_HASH == "0123456789abcdef0123456789abcdef":
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!! ERROR: Please replace API_ID and API_HASH with your own. !!!")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    else:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            print("\nShutting down userbot.")
            if app.is_connected:
                asyncio.run(app.stop())
            if voice_client.is_connected:
                asyncio.run(voice_client.stop())
  
