import os
import logging
from flask import Flask, render_template, request, jsonify, send_from_directory
from dotenv import load_dotenv
import sys
import sqlite3
from datetime import datetime

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

@app.route('/scorecard')
def scorecard():
    """Render the scorecard page with real model performance data"""
    try:
        # Get the database path (same as your chatbot uses)
        db_path = os.environ.get('DB_PATH', '../data/db/mental_form.db')
        
        # Get model performance data
        performance_data = get_model_performance_data(db_path)
        
        return render_template('scorecard.html', data=performance_data)
    
    except Exception as e:
        logger.error(f"Error loading scorecard data: {e}")
        # Return with empty/default data if there's an error
        default_data = {
            'overview': {
                'total_bets': 0,
                'win_rate': 0,
                'roi': 0,
                'profit_loss_units': 0,
                'avg_stake_units': 0,
                'avg_odds': 0
            },
            'bet_history': []
        }
        return render_template('scorecard.html', data=default_data)

def get_model_performance_data(db_path):
    """Get model performance data from the database - based on your data retriever logic"""
    
    def get_db_connection():
        """Get database connection with proper error handling"""
        try:
            if not os.path.exists(db_path):
                logger.error(f"Database file not found: {db_path}")
                return None
                
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row  # Enable column access by name
            return conn
        except Exception as e:
            logger.error(f"Error connecting to database: {e}")
            return None
    
    conn = get_db_connection()
    if not conn:
        return {'overview': {}, 'bet_history': []}
    
    try:
        cursor = conn.cursor()
        
        # Get overall statistics (copied from your _retrieve_model_performance method)
        cursor.execute('''
        SELECT 
            COUNT(*) as total_bets,
            SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as winning_bets,
            SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losing_bets,
            SUM(stake) as total_staked,
            SUM(CASE WHEN outcome IN ('win', 'loss') THEN profit_loss ELSE 0 END) as total_profit_loss,
            AVG(stake) as avg_stake,
            AVG(odds) as avg_odds,
            AVG(expected_value) as avg_ev
        FROM bets
        WHERE outcome IN ('win', 'loss')
        ''')
        
        stats = cursor.fetchone()
        overview = {}
        
        if stats:
            stats_dict = dict(stats)
            total_bets = stats_dict['total_bets'] or 0
            winning_bets = stats_dict['winning_bets'] or 0
            total_staked = stats_dict['total_staked'] or 0
            total_profit_loss = stats_dict['total_profit_loss'] or 0
            
            # Calculate ROI and Win Rate
            roi = (total_profit_loss / total_staked * 100) if total_staked > 0 else 0
            
            # Convert to units (1 unit = $10)
            profit_loss_units = total_profit_loss / 10
            avg_stake_units = (stats_dict['avg_stake'] or 0) / 10

            # Format average odds to American format
            avg_odds_decimal = stats_dict['avg_odds'] or 0
            if avg_odds_decimal >= 2.0:
                avg_odds_american = f"+{int((avg_odds_decimal - 1) * 100)}"
            elif avg_odds_decimal > 1.0:
                avg_odds_american = f"{int(-100 / (avg_odds_decimal - 1))}"
            else:
                avg_odds_american = "N/A"
            
            overview = {
                'total_bets': total_bets,
                'winning_bets': winning_bets,
                'losing_bets': stats_dict['losing_bets'] or 0,
                'roi': round(roi, 1),
                'profit_loss_units': round(profit_loss_units, 1),
                'avg_stake_units': round(avg_stake_units, 1),
                'avg_odds_american': avg_odds_american,
                'avg_ev': round(stats_dict['avg_ev'] or 0, 1)
            }
        
        # Get individual bet history (copied from your method)
        cursor.execute('''
        SELECT 
            b.event_name,
            b.player_name,
            b.bet_market,
            b.stake,
            b.odds,
            b.profit_loss,
            b.mental_form_score,
            b.expected_value,
            b.placed_date,
            b.settled_date,
            b.is_dead_heat,
            b.outcome,
            tr.course_name
        FROM bets b
        LEFT JOIN (
            SELECT DISTINCT event_name, year, course_name 
            FROM tournament_results 
            WHERE course_name IS NOT NULL
        ) tr ON b.event_name = tr.event_name
            AND CAST(strftime('%Y', b.placed_date) AS INTEGER) = tr.year
        WHERE b.outcome IN ('win', 'loss')
        ORDER BY b.settled_date DESC
        LIMIT 200
        ''')
        
        bet_history = []
        for bet in cursor.fetchall():
            bet_dict = dict(bet)
            
            # Convert stake and profit/loss to units
            stake_units = bet_dict['stake'] / 10
            profit_loss_units = bet_dict['profit_loss'] / 10
            
            # Format American odds
            decimal_odds = bet_dict['odds']
            if decimal_odds >= 2.0:
                american_odds = f"+{int((decimal_odds - 1) * 100)}"
            else:
                american_odds = f"{int(-100 / (decimal_odds - 1))}"
            
            # Format market name
            market = bet_dict['bet_market']
            if market:
                market_display = market.replace('_', ' ').title()
            else:
                market_display = market
                
            # Format profit/loss with proper sign and dead heat notation
            if bet_dict['is_dead_heat'] and bet_dict['outcome'] == 'win':
                if profit_loss_units >= 0:
                    profit_loss_display = f"+{profit_loss_units:.1f}u (DH)"
                else:
                    profit_loss_display = f"{profit_loss_units:.1f}u (DH)"
            else:
                if profit_loss_units >= 0:
                    profit_loss_display = f"+{profit_loss_units:.1f}u"
                else:
                    profit_loss_display = f"{profit_loss_units:.1f}u"

            # Format date to American format (MM/DD/YYYY)
            settled_date = bet_dict['settled_date']
            if settled_date:
                try:
                    # Parse the date (assuming it's in YYYY-MM-DD format)
                    if ' ' in settled_date:
                        settled_date = settled_date.split(' ')[0]  # Remove time if present
                    
                    date_obj = datetime.strptime(settled_date, '%Y-%m-%d')
                    settled_date = date_obj.strftime('%m/%d/%y')  # Convert to MM/DD/YY
                except ValueError:
                    # If parsing fails, keep original format
                    pass
            
            bet_history.append({
                'event_name': bet_dict['event_name'],
                'course_name': bet_dict['course_name'] or 'Unknown',
                'player_name': bet_dict['player_name'],
                'bet_market': market_display,
                'stake_units': round(stake_units, 1),
                'american_odds': american_odds,
                'profit_loss_display': profit_loss_display,
                'profit_loss_units': profit_loss_units,
                'mental_form_score': bet_dict['mental_form_score'],
                'ev': round(bet_dict['expected_value'] or 0, 1),
                'placed_date': bet_dict['placed_date'],
                'settled_date': settled_date,
                'outcome': bet_dict['outcome']
            })
        
        return {
            'overview': overview,
            'bet_history': bet_history
        }
        
    except Exception as e:
        logger.error(f"Error retrieving model performance data: {e}")
        return {'overview': {}, 'bet_history': []}
    finally:
        if conn:
            conn.close()

@app.route('/api/scorecard-data')
def scorecard_data():
    """API endpoint to return scorecard data as JSON"""
    try:
        # Get the database path (same as your chatbot uses)
        db_path = os.environ.get('DB_PATH', '../data/db/mental_form.db')
        
        # Get model performance data using your existing function
        performance_data = get_model_performance_data(db_path)
        
        return jsonify(performance_data)
    
    except Exception as e:
        logger.error(f"Error loading scorecard API data: {e}")
        # Return empty/default data if there's an error
        default_data = {
            'overview': {
                'total_bets': 0,
                'win_rate': 0,
                'roi': 0,
                'profit_loss_units': 0,
                'avg_stake_units': 0,
                'avg_odds': 0
            },
            'bet_history': []
        }
        return jsonify(default_data)

@app.route('/favicon.ico')
@app.route('/favicon.png')
def favicon():
    """Serve the favicon from the root directory"""
    # Check which file exists
    import os
    
    # Try .ico first, then .png
    for filename, mimetype in [
        ('favicon.ico', 'image/vnd.microsoft.icon'),
        ('favicon.png', 'image/png')
    ]:
        if os.path.exists(os.path.join(app.root_path, filename)):
            return send_from_directory(
                app.root_path, 
                filename, 
                mimetype=mimetype
            )
    
    # If no favicon found, return 404
    from flask import abort
    abort(404)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)