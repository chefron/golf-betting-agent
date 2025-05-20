import os
import logging
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import sys

# Add parent directory to path to find the modules
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)  # Add the root directory
sys.path.append(os.path.join(project_root, 'chatbot'))  # Add the chatbot directory specifically

# Then import using the absolute path
from chatbot.head_pro_chatbot import HeadProChatbot

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("headpro_site.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("headpro_site")

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev_key_for_testing')

# Initialize chatbot
chatbot = None

def get_chatbot():
    global chatbot
    if chatbot is None:
        try:
            db_path = os.environ.get('DB_PATH', '../data/db/mental_form.db')
            persona_file = os.environ.get('PERSONA_FILE', '../chatbot/head_pro_persona.txt')
            chatbot = HeadProChatbot(db_path=db_path, persona_file=persona_file)
            logger.info("Chatbot initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing chatbot: {e}")
            import traceback
            logger.error(traceback.format_exc())
    return chatbot

# Routes
@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    """API endpoint for chat messages"""
    try:
        # Get chatbot instance
        chatbot_instance = get_chatbot()
        if not chatbot_instance:
            return jsonify({
                "response": "The Head Pro is currently unavailable. Please try again in a moment.",
                "error": "Chatbot initialization failed"
            }), 500
        
        # Get request data
        data = request.json
        if not data:
            return jsonify({
                "response": "Your message was empty. Try asking the Head Pro a question.",
                "error": "No data provided"
            }), 400
        
        user_id = data.get('user_id', f'web_user_{request.remote_addr}')
        message = data.get('message')
        
        if not message:
            return jsonify({
                "response": "Your message was empty. Try asking the Head Pro a question.",
                "error": "No message provided"
            }), 400
        
        # Process the message
        logger.info(f"Processing message from user {user_id}: {message}")
        response = chatbot_instance.process_message(user_id, message)
        
        return jsonify(response)
    
    except Exception as e:
        logger.error(f"Error processing chat request: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            "response": "The Head Pro is having technical difficulties. Something about the 19th hole and his flask...",
            "error": str(e)
        }), 500

@app.route('/api/reset', methods=['POST'])
def reset_chat():
    """API endpoint to reset conversation history"""
    try:
        chatbot_instance = get_chatbot()
        if not chatbot_instance:
            return jsonify({"status": "error", "message": "Chatbot unavailable"}), 500
        
        data = request.json
        user_id = data.get('user_id', f'web_user_{request.remote_addr}')
        
        result = chatbot_instance.reset_conversation(user_id)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error resetting conversation: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)