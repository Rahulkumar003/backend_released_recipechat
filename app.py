import asyncio
from flask import Flask, request, jsonify, current_app, copy_current_request_context
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from recipe_chatbot import RecipeChatBot

app = Flask(__name__)

# Update allowed origins to include your deployed frontend URL
allowed_origins = [
    "http://192.168.56.1:3000",  # Local development
    "https://recipechat.netlify.app",  # Deployed frontend
]
CORS(app, supports_credentials=True, origins=allowed_origins)

# Update SocketIO configuration
socketio = SocketIO(
    app, 
    cors_allowed_origins=allowed_origins,
    async_mode='threading',
    logger=True,
    engineio_logger=True
)

# Initialize the chatbot
chatbot = RecipeChatBot()

# Add a dictionary to track generation status for each client
generation_status = {}

@socketio.on('connect')
def handle_connect():
    print("Client connected")
    generation_status[request.sid] = {"should_stop": False}

@socketio.on('disconnect')
def handle_disconnect():
    print("Client disconnected")
    if request.sid in generation_status:
        del generation_status[request.sid]

@socketio.on('stop_generation')
def handle_stop_generation():
    if request.sid in generation_status:
        generation_status[request.sid]["should_stop"] = True
        # Clear any ongoing processes for this client
        chatbot.clear_conversation()  # Add this method to your RecipeChatBot class
    emit('response', {"complete": True})

@socketio.on('generate_text')
def generate_text(data):
    print("Received generate_text event with data:", data)
    prompt = data.get('prompt')
    if not prompt:
        emit('response', {"error": "No prompt provided"})
        return

    # Store the session ID at the beginning of the request
    session_id = request.sid

    @copy_current_request_context
    def run_async_generator():
        try:
            async def stream_words():
                async for word in chatbot.ask_question_stream(prompt):
                    if generation_status.get(session_id, {}).get("should_stop", False):
                        break
                    socketio.emit('response', {
                        "data": word,
                        "streaming": True
                    }, room=session_id)
                    await asyncio.sleep(0.1)
            
            asyncio.run(stream_words())
            socketio.emit('response', {"complete": True}, room=session_id)

        except Exception as e:
            print(f"Error in stream_text: {str(e)}")
            socketio.emit('response', {"error": str(e)}, room=session_id)

    socketio.start_background_task(run_async_generator)

@socketio.on('fetch_recipe_stream')
def fetch_recipe_stream(data):
    print("Received fetch_recipe_stream event with data:", data)
    video_url = data.get('video_url')
    if not video_url:
        emit('recipe_stream', {"error": "Video URL is required"})
        return

    # Store the session ID at the beginning of the request
    session_id = request.sid

    def run_async_stream():
        try:        
            async def stream_recipe():
                try:
                    async for chunk in chatbot.fetch_recipe(video_url):
                        # Use the stored session ID instead of accessing request.sid
                        if generation_status.get(session_id, {}).get("should_stop", False):
                            break
                        socketio.emit('recipe_stream', {
                            "data": chunk, 
                            "streaming": True
                        }, room=session_id)
                    
                    socketio.emit('recipe_stream', {"complete": True}, room=session_id)
                
                except Exception as e:
                    print(f"Error streaming recipe: {str(e)}")
                    socketio.emit('recipe_stream', {"error": str(e)}, room=session_id)

            asyncio.run(stream_recipe())

        except Exception as e:
            print(f"Error in fetch_recipe_stream: {str(e)}")
            socketio.emit('recipe_stream', {"error": str(e)}, room=session_id)

    socketio.start_background_task(run_async_stream)

if __name__ == '__main__':
    # Bind to all network interfaces
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
