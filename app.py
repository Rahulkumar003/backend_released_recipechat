import asyncio
from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from recipe_chatbot import RecipeChatBot
app = Flask(__name__)

# Update allowed origins to include your deployed frontend URL
allowed_origins = [
    "http://localhost:3000",  # Local development
    # "http://192.168.1.20:3000",  # Local development
    "https://recipechat.netlify.app",  # Deployed frontend
]
CORS(app, supports_credentials=True, origins=allowed_origins)

# Update SocketIO configuration
socketio = SocketIO(
    app, 
    cors_allowed_origins=allowed_origins,
    async_mode='threading',  # or 'gevent'
    logger=True,
    engineio_logger=True,
    ping_timeout=60,  # Increase to prevent premature disconnection
    ping_interval=25
)
# Initialize the chatbot
chatbot = RecipeChatBot()

@socketio.on('connect')
def handle_connect():
    print("Client connected")

@socketio.on('disconnect')
def handle_disconnect():
    print("Client disconnected")
    
@socketio.on('generate_text')
def generate_text(data):
    print("Received generate_text event with data:", data)
    prompt = data.get('prompt')
    if not prompt:
        emit('response', {"error": "No prompt provided"})
        return

    async def stream_words():
        try:
            async for word in chatbot.ask_question_stream(prompt):
                try:
                    socketio.emit('response', {
                        "data": word,
                        "streaming": True
                    })
                except (OSError, ConnectionError) as e:
                    print(f"Socket error during emit: {e}")
                    socketio.emit('response', {"error": "Connection error during streaming"})
                    return
                await asyncio.sleep(0.1)
            socketio.emit('response', {"complete": True})
        except Exception as e:
            print(f"Error in stream_text: {str(e)}")
            socketio.emit('response', {"error": str(e)})

    def run_async_task():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(stream_words())
        finally:
            loop.close()

    socketio.start_background_task(run_async_task)    

@socketio.on('fetch_recipe_stream')
def fetch_recipe_stream(data):
    print("Received fetch_recipe_stream event with data:", data)
    video_url = data.get('video_url')
    if not video_url:
        emit('recipe_stream', {"error": "Video URL is required"})
        return

    def run_async_stream():
        try:        
            async def stream_recipe():
                try:
                    async for chunk in chatbot.fetch_recipe(video_url):
                        print(f"Streaming recipe chunk: {chunk}")
                        socketio.emit('recipe_stream', {
                            "data": chunk, 
                            "streaming": True
                        })
                    
                    socketio.emit('recipe_stream', {"complete": True})
                
                except Exception as e:
                    print(f"Error streaming recipe: {str(e)}")
                    socketio.emit('recipe_stream', {"error": str(e)})

            asyncio.run(stream_recipe())

        except Exception as e:
            print(f"Error in fetch_recipe_stream: {str(e)}")
            socketio.emit('recipe_stream', {"error": str(e)})

    socketio.start_background_task(run_async_stream)

if __name__ == '__main__':
    # Bind to all network interfaces
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
