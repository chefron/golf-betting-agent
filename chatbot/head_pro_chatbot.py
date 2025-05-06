import os
import logging
import json
from typing import Dict, List, Any
from datetime import datetime
from dotenv import load_dotenv

from query_analysis_agent import QueryAnalysisAgent
from data_retrieval_orchestrator import DataRetrievalOrchestrator
from response_generator import ResponseGenerator

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("head_pro_chatbot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("head_pro.app")

class HeadProChatbot:
    def __init__(self, db_path: str = "../data/db/mental_form.db", persona_file: str = "head_pro_persona.txt"):
        """Initialize the Head Pro chatbot."""
        # Get API key
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Anthropic API key is required but not found in environment variables")
        
        # Initialize data retriever first to get current tournament
        self.data_retriever = DataRetrievalOrchestrator(db_path)
        self.current_tournament = self.data_retriever.current_tournament
        
        # Initialize other components
        self.query_analyzer = QueryAnalysisAgent(self.api_key, self.current_tournament)
        self.response_generator = ResponseGenerator(self.api_key, persona_file)
        
        # Conversation history storage
        self.conversations = {}
        
        logger.info(f"Head Pro chatbot initialized with current tournament: {self.current_tournament}")
    
    def process_message(self, user_id: str, message: str) -> Dict[str, Any]:
        """Process a user message and generate a response."""
        logger.info(f"Processing message from user {user_id}: {message}")
        
        start_time = datetime.now()
        
        # Initialize or get the user's conversation history
        if user_id not in self.conversations:
            self.conversations[user_id] = []
        
        conversation_history = self.conversations[user_id]
        
        try:
            # Step 1: Analyze the query with our simplified decision tree
            logger.info("Analyzing query...")
            query_info = self.query_analyzer.analyze_query(message, conversation_history)
            logger.info(f"Query analysis result: {json.dumps(query_info)}")
            
            # Step 2: Retrieve relevant data based on the decision tree result
            logger.info(f"Retrieving data for query type: {query_info.get('query_type', 'unknown')}")
            retrieved_data = self.data_retriever.retrieve_data(query_info)
            
            # Step 3: Generate response using the retrieved data
            logger.info("Generating response...")
            response_text = self.response_generator.generate_response(
                message, retrieved_data, conversation_history
            )
            
            # Update conversation history
            conversation_history.append({"role": "user", "content": message, "timestamp": datetime.now().isoformat()})
            conversation_history.append({"role": "assistant", "content": response_text, "timestamp": datetime.now().isoformat()})
            
            # Limit conversation history length
            if len(conversation_history) > 20:
                conversation_history = conversation_history[-20:]
            
            self.conversations[user_id] = conversation_history
            
            # Calculate processing time
            processing_time = (datetime.now() - start_time).total_seconds()
            
            return {
                "response": response_text,
                "metadata": {
                    "query_type": query_info.get("query_type", "unknown"),
                    "processing_time": processing_time,
                    "response_timestamp": datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Generate a fallback response
            fallback_response = "I'm on my third whiskey and the neural connections aren't firing like they should. Try asking something else, preferably something that doesn't require me to access my mental database right now."
            
            # Update conversation history
            conversation_history.append({"role": "user", "content": message, "timestamp": datetime.now().isoformat()})
            conversation_history.append({"role": "assistant", "content": fallback_response, "timestamp": datetime.now().isoformat()})
            
            self.conversations[user_id] = conversation_history
            
            return {
                "response": fallback_response,
                "metadata": {
                    "error": str(e),
                    "response_timestamp": datetime.now().isoformat()
                }
            }
    
    def reset_conversation(self, user_id: str) -> Dict[str, Any]:
        """Reset a user's conversation history."""
        if user_id in self.conversations:
            self.conversations[user_id] = []
            return {"status": "success", "message": "Conversation reset successfully"}
        else:
            return {"status": "success", "message": "No conversation to reset"}

def cli():
    """Command-line interface for testing the chatbot"""
    print("=== HEAD PRO CHATBOT CLI ===")
    print("Type 'exit' to quit, 'reset' to start a new conversation")
    
    try:
        chatbot = HeadProChatbot()
    except Exception as e:
        print(f"Error initializing chatbot: {e}")
        return
    
    user_id = f"cli_user_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    while True:
        try:
            # Get user input
            message = input("\nYou: ").strip()
            
            # Check for exit command
            if message.lower() == 'exit':
                print("Goodbye!")
                break
            
            # Check for reset command
            if message.lower() == 'reset':
                chatbot.reset_conversation(user_id)
                print("Conversation reset. Starting fresh.")
                continue
            
            # Skip empty messages
            if not message:
                continue
            
            # Process message
            print("\nProcessing... (this may take a moment)")
            response = chatbot.process_message(user_id, message)
            
            # Print response
            print(f"\nHead Pro: {response['response']}")
            
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"\nError: {e}")

# Flask web server implementation
def create_flask_app():
    """Create Flask app for the web API"""
    from flask import Flask, request, jsonify
    
    app = Flask(__name__)
    chatbot = None
    
    @app.route('/api/chat', methods=['POST'])
    def chat():
        """API endpoint for chat messages"""
        nonlocal chatbot
        
        # Initialize chatbot if not already done
        if not chatbot:
            try:
                chatbot = HeadProChatbot()
            except Exception as e:
                return jsonify({"error": f"Failed to initialize chatbot: {str(e)}"}), 500
        
        # Get request data
        data = request.json
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        user_id = data.get('user_id')
        message = data.get('message')
        
        if not user_id or not message:
            return jsonify({"error": "Missing required fields: user_id, message"}), 400
        
        # Process the message
        response = chatbot.process_message(user_id, message)
        
        return jsonify(response)
    
    @app.route('/api/reset', methods=['POST'])
    def reset():
        """API endpoint to reset conversation history"""
        nonlocal chatbot
        
        # Initialize chatbot if not already done
        if not chatbot:
            try:
                chatbot = HeadProChatbot()
            except Exception as e:
                return jsonify({"error": f"Failed to initialize chatbot: {str(e)}"}), 500
        
        # Get request data
        data = request.json
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        user_id = data.get('user_id')
        
        if not user_id:
            return jsonify({"error": "Missing required field: user_id"}), 400
        
        # Reset the conversation
        response = chatbot.reset_conversation(user_id)
        
        return jsonify(response)
    
    return app

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'web':
        # Run the web app
        app = create_flask_app()
        app.run(host='0.0.0.0', port=5000, debug=True)
    else:
        # Run the CLI
        cli()