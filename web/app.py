from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3
import os
import sys
from datetime import datetime

# Add parent directory to path to find the modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from insights_extractor import create_claude_prompt, query_claude, parse_claude_response, get_player_by_name
from odds_retriever import OddsRetriever, format_market_name
from db_utils import (
    get_db_connection, 
    add_insight, 
    calculate_mental_form, 
    search_players
)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev_key_for_testing")

app.config['ANTHROPIC_API_KEY'] = os.environ.get('ANTHROPIC_API_KEY')
app.config['DATAGOLF_API_KEY'] = os.environ.get('DATAGOLF_API_KEY')

# Default database path - resolves to the correct location from the web directory
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data/db/mental_form.db")

# Add the current date to all templates
@app.context_processor
def inject_now():
    return {'now': datetime.now()}

# Helper functions
def get_dashboard_stats():
    """Get basic statistics for dashboard"""
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    
    # Get players with mental form scores
    cursor.execute("SELECT COUNT(*) FROM mental_form")
    mental_form_count = cursor.fetchone()[0]
    
    # Get top 5 players by mental form score
    cursor.execute("""
    SELECT p.id, p.name, m.score 
    FROM mental_form m
    JOIN players p ON m.player_id = p.id
    ORDER BY m.score DESC
    LIMIT 5
    """)
    top_players = cursor.fetchall()
    
    # Get bottom 5 players by mental form score
    cursor.execute("""
    SELECT p.id, p.name, m.score 
    FROM mental_form m
    JOIN players p ON m.player_id = p.id
    ORDER BY m.score ASC
    LIMIT 5
    """)
    bottom_players = cursor.fetchall()
    
    # Get recently updated players
    cursor.execute("""
    SELECT p.id, p.name, m.score, m.last_updated
    FROM mental_form m
    JOIN players p ON m.player_id = p.id
    ORDER BY m.last_updated DESC
    LIMIT 5
    """)
    recent_updates = cursor.fetchall()
    
    conn.close()
    
    return {
        "mental_form_count": mental_form_count,
        "top_players": top_players,
        "bottom_players": bottom_players,
        "recent_updates": recent_updates
    }

# Routes
@app.route('/')
def index():
    """Dashboard page"""
    stats = get_dashboard_stats()
    return render_template('index.html', stats=stats, now=datetime.now())

@app.route('/players')
def players():
    """List all players with filtering options"""
    # Get query parameters for filtering
    search_name = request.args.get('name', '')
    sort_by = request.args.get('sort', 'name')
    order = request.args.get('order', 'asc')
    
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    
    # Base query
    query = """
    SELECT p.id, p.name, p.country, p.amateur, m.score, 
           (SELECT COUNT(*) FROM insights i WHERE i.player_id = p.id) as insight_count,
           m.last_updated
    FROM players p
    LEFT JOIN mental_form m ON p.id = m.player_id
    """
    
    params = []
    
    # Add search filter if provided
    if search_name:
        query += " WHERE LOWER(p.name) LIKE LOWER(?)"
        params.append(f"%{search_name}%")
    
    # Add sorting
    if sort_by == 'mental_form':
        sort_column = 'm.score'
    elif sort_by == 'insights':
        sort_column = 'insight_count'
    else:
        sort_column = f'p.{sort_by}'
    
    query += f" ORDER BY {sort_column}"
    
    if order.lower() == 'desc':
        query += " DESC"
    
    # Add limit to avoid loading too many players at once
    query += " LIMIT 100"
    
    cursor.execute(query, params)
    player_list = cursor.fetchall()
    
    conn.close()
    
    return render_template('players.html', players=player_list, 
                          search_name=search_name, sort_by=sort_by, order=order)

@app.route('/player/<int:player_id>')
def player_detail(player_id):
    """Show details for a specific player"""
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    
    # Get player info
    cursor.execute("""
    SELECT p.*, m.score, m.justification, m.last_updated
    FROM players p
    LEFT JOIN mental_form m ON p.id = m.player_id
    WHERE p.id = ?
    """, (player_id,))
    player = cursor.fetchone()
    
    if not player:
        conn.close()
        flash('Player not found!', 'error')
        return redirect(url_for('players'))
    
    # Get player insights
    cursor.execute("""
    SELECT * FROM insights
    WHERE player_id = ?
    ORDER BY date DESC
    """, (player_id,))
    insights = cursor.fetchall()
    
    # Get mental form history
    cursor.execute("""
    SELECT * FROM mental_form_history
    WHERE player_id = ?
    ORDER BY date ASC
    """, (player_id,))
    history = cursor.fetchall()
    
    conn.close()
    
    return render_template('player_detail.html', player=player, 
                          insights=insights, history=history)

@app.route('/calculate_mental_form/<int:player_id>', methods=['POST'])
def recalculate_mental_form(player_id):
    """Recalculate mental form for a player"""
    try:
        print(f"Database path: {DB_PATH}")
        print(f"Database exists: {os.path.exists(DB_PATH)}")
        print(f"Current working directory: {os.getcwd()}")

        score, justification = calculate_mental_form(player_id)

        flash(f'Mental form recalculated: {score}', 'success')
    except Exception as e:
        flash(f'Error calculating mental form: {str(e)}', 'error')
        import traceback
        print(traceback.format_exc())  # Print full stack trace
    
    return redirect(url_for('player_detail', player_id=player_id))

@app.route('/insights')
def insights():
    """Manage insights"""
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    
    # Get query parameters for filtering
    player_name = request.args.get('player', '')
    source = request.args.get('source', '')
    
    # Base query
    query = """
    SELECT i.*, p.name as player_name
    FROM insights i
    JOIN players p ON i.player_id = p.id
    WHERE 1=1
    """
    
    params = []
    
    # Add filters if provided
    if player_name:
        query += " AND LOWER(p.name) LIKE LOWER(?)"
        params.append(f"%{player_name}%")
    
    if source:
        query += " AND LOWER(i.source) LIKE LOWER(?)"
        params.append(f"%{source}%")
    
    # Add sorting
    query += " ORDER BY i.date DESC LIMIT 100"
    
    cursor.execute(query, params)
    insight_list = cursor.fetchall()
    
    # Get unique sources for filter dropdown
    cursor.execute("SELECT DISTINCT source FROM insights ORDER BY source")
    sources = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    
    return render_template('insights.html', insights=insight_list, 
                          sources=sources, player_filter=player_name, source_filter=source)

@app.route('/add_insight', methods=['GET', 'POST'])
def add_new_insight():
    """Add a new insight manually"""
    if request.method == 'POST':
        player_name = request.form.get('player_name')
        text = request.form.get('text')
        source = request.form.get('source')
        source_type = request.form.get('source_type')
        content_title = request.form.get('content_title', '')
        content_url = request.form.get('content_url', '')
        date = request.form.get('date') or datetime.now().strftime("%Y-%m-%d")
        
        # Find player
        conn = get_db_connection(DB_PATH)
        player = get_player_by_name(conn, player_name)
        conn.close()
        
        if not player:
            flash(f'Player not found: {player_name}', 'error')
            return redirect(url_for('add_new_insight'))
        
        player_id = player['id']
        
        # Add the insight
        try:
            insight_id = add_insight(
                player_id=player_id,
                text=text,
                source=source,
                source_type=source_type,
                content_title=content_title,
                content_url=content_url,
                date=date
            )
            flash(f'Insight added successfully for {player_name}', 'success')
            return redirect(url_for('player_detail', player_id=player_id))
        except Exception as e:
            flash(f'Error adding insight: {str(e)}', 'error')
            return redirect(url_for('add_new_insight'))
    
    # GET request - show form
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    
    # Get sources for dropdown
    cursor.execute("SELECT DISTINCT source FROM insights ORDER BY source")
    sources = [row[0] for row in cursor.fetchall()]
    
    # Get source types for dropdown
    cursor.execute("SELECT DISTINCT source_type FROM insights ORDER BY source_type")
    source_types = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    
    # Get parameters from URL query string (for pre-filling form)
    player_name = request.args.get('player_name', '')
    text = request.args.get('text', '')
    source = request.args.get('source', '')
    source_type = request.args.get('source_type', 'podcast')  # Default to podcast
    content_title = request.args.get('content_title', '')
    content_url = request.args.get('content_url', '')
    
    return render_template('add_insight.html', 
                          sources=sources, 
                          source_types=source_types,
                          player_name=player_name,
                          text=text,
                          source=source,
                          source_type=source_type,
                          content_title=content_title,
                          content_url=content_url,
                          today=datetime.now().strftime("%Y-%m-%d"))

@app.route('/edit_insight/<int:insight_id>', methods=['GET', 'POST'])
def edit_insight(insight_id):
    """Edit an existing insight"""
    conn = get_db_connection(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if request.method == 'POST':
        text = request.form.get('text')
        player_name = request.form.get('player_name')  # Get the potentially updated player name
        source = request.form.get('source')
        source_type = request.form.get('source_type')
        content_title = request.form.get('content_title', '')
        content_url = request.form.get('content_url', '')
        date = request.form.get('date')
        
        # First, get the original player_id for the insight
        cursor.execute("SELECT player_id FROM insights WHERE id = ?", (insight_id,))
        original_player = cursor.fetchone()
        
        if not original_player:
            conn.close()
            flash('Insight not found!', 'error')
            return redirect(url_for('insights'))
        
        original_player_id = original_player['player_id']
        new_player_id = original_player_id  # Default to keeping the same player
        
        # Check if the player name has been changed
        cursor.execute("SELECT p.name FROM players p WHERE p.id = ?", (original_player_id,))
        original_player_name_result = cursor.fetchone()
        original_player_name = original_player_name_result['name'] if original_player_name_result else "Unknown"
        
        if player_name != original_player_name:
            # Try to find the new player
            player = get_player_by_name(conn, player_name)
            
            if player:
                new_player_id = player['id']
                print(f"Changing player assignment from {original_player_id} ({original_player_name}) to {new_player_id} ({player_name})")
            else:
                conn.close()
                flash(f'Player not found: {player_name}. Insight will remain assigned to {original_player_name}.', 'error')
                return redirect(url_for('edit_insight', insight_id=insight_id))
        
        # Update the insight
        cursor.execute("""
        UPDATE insights
        SET text = ?, player_id = ?, source = ?, source_type = ?, content_title = ?, content_url = ?, date = ?
        WHERE id = ?
        """, (text, new_player_id, source, source_type, content_title, content_url, date, insight_id))
        
        # Mark mental form for recalculation for both original and new player (if different)
        cursor.execute("""
        UPDATE mental_form
        SET last_updated = NULL
        WHERE player_id = ?
        """, (original_player_id,))
        
        if new_player_id != original_player_id:
            cursor.execute("""
            UPDATE mental_form
            SET last_updated = NULL
            WHERE player_id = ?
            """, (new_player_id,))
        
        conn.commit()
        conn.close()
        
        flash('Insight updated successfully', 'success')
        return redirect(url_for('player_detail', player_id=new_player_id))
    
    # GET request - show form with existing data
    cursor.execute("""
    SELECT i.*, p.name as player_name
    FROM insights i
    JOIN players p ON i.player_id = p.id
    WHERE i.id = ?
    """, (insight_id,))
    insight = cursor.fetchone()
    
    if not insight:
        conn.close()
        flash('Insight not found!', 'error')
        return redirect(url_for('insights'))
    
    # Get sources for dropdown
    cursor.execute("SELECT DISTINCT source FROM insights ORDER BY source")
    sources = [row[0] for row in cursor.fetchall()]
    
    # Get source types for dropdown
    cursor.execute("SELECT DISTINCT source_type FROM insights ORDER BY source_type")
    source_types = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    
    return render_template('edit_insight.html', insight=insight, 
                          sources=sources, source_types=source_types)

@app.route('/delete_insight/<int:insight_id>', methods=['POST'])
def delete_insight(insight_id):
    """Delete an insight"""
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    
    # Get player_id for redirect
    cursor.execute("SELECT player_id FROM insights WHERE id = ?", (insight_id,))
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        flash('Insight not found!', 'error')
        return redirect(url_for('insights'))
    
    player_id = result[0]
    
    # Delete the insight
    cursor.execute("DELETE FROM insights WHERE id = ?", (insight_id,))
    
    # Mark mental form for recalculation
    cursor.execute("""
    UPDATE mental_form
    SET last_updated = NULL
    WHERE player_id = ?
    """, (player_id,))
    
    conn.commit()
    conn.close()
    
    flash('Insight deleted successfully', 'success')
    return redirect(url_for('player_detail', player_id=player_id))

@app.route('/process', methods=['GET', 'POST'])
def process_transcript():
    """Process a transcript to extract insights"""
    if request.method == 'POST':
        transcript_text = request.form.get('transcript')
        event_name = request.form.get('event_name')
        source = request.form.get('source')
        source_type = request.form.get('source_type', 'podcast')
        episode_title = request.form.get('episode_title', '')
        content_url = request.form.get('content_url', '')
        insight_date = request.form.get('insight_date', datetime.now().strftime("%Y-%m-%d"))
        
        if not transcript_text or not event_name or not source:
            flash('Please fill out all required fields', 'error')
            return redirect(url_for('process_transcript'))
        
        try:
            # Get API key from environment
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                flash("Error: No Claude API key provided. Set ANTHROPIC_API_KEY env variable", 'error')
                return redirect(url_for('process_transcript'))
            
            # Create prompt and query Claude
            prompt = create_claude_prompt(transcript_text, event_name)
            claude_response = query_claude(prompt, api_key)
            
            # Parse response to get insights
            insights = parse_claude_response(claude_response)
            
            # Store extracted insights for the template
            extracted_insights = []
            
            # Connect to database
            conn = get_db_connection(DB_PATH)
            conn.row_factory = sqlite3.Row
            
            # Process each insight
            for insight_item in insights:
                player_name = insight_item["player_name"]
                insight_text = insight_item["insight"]

                # Create the insight data structure
                insight_data = {
                    'player_name': player_name,
                    'text': insight_text,
                    'matched': False,
                    'player_id': None
    }
                
                # Try to find the player in the database
                player = get_player_by_name(conn, player_name)

                if player:
                    # Add insight to database
                    player_id = player["id"]
                    add_insight(
                        player_id=player_id,
                        text=insight_text,
                        source=source,
                        source_type=source_type,
                        content_title=episode_title,
                        content_url=content_url,
                        date=insight_date
                    )
                    insight_data['matched'] = True
                    insight_data['player_id'] = player_id
                
                extracted_insights.append(insight_data)
            
            conn.close()
            
            return render_template('process_results.html', 
                                 insights=extracted_insights,
                                 event_name=event_name,
                                 source=source,
                                 source_type=source_type,
                                 content_title=episode_title,
                                 content_url=content_url,
                                 insight_date=insight_date)
                
        except Exception as e:
            flash(f'Error processing transcript: {str(e)}', 'error')
            return redirect(url_for('process_transcript'))
    
    # GET request - show form
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    
    # Get sources for dropdown
    cursor.execute("SELECT DISTINCT source FROM insights WHERE source != '' ORDER BY source")
    sources = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    
    return render_template('process.html', sources=sources, today=datetime.now().strftime("%Y-%m-%d"))

@app.route('/fetch_youtube_transcript', methods=['POST'])
def fetch_youtube_transcript():
    """Fetch transcript from a YouTube video URL"""
    try:
        # Get YouTube URL from form
        youtube_url = request.form.get('youtube_url')
        if not youtube_url:
            return jsonify({'success': False, 'error': 'No YouTube URL provided'})
        
        # Import the necessary functions from youtube_transcript.py
        from youtube_transcript import get_video_id_from_url, get_transcript, format_transcript
        
        # Get video ID from URL
        video_id = get_video_id_from_url(youtube_url)
        
        # Get transcript
        transcript_list = get_transcript(video_id)
        if not transcript_list:
            return jsonify({
                'success': False, 
                'error': 'Failed to fetch transcript. Make sure the video has closed captions available.'
            })
        
        # Format transcript
        transcript_text = format_transcript(transcript_list)
        
        # Try to get video title using pytube (optional)
        video_title = None
        try:
            from pytube import YouTube
            yt = YouTube(youtube_url)
            video_title = yt.title
        except:
            # If pytube fails, just continue without the title
            pass
        
        return jsonify({
            'success': True, 
            'transcript': transcript_text,
            'video_title': video_title
        })
        
    except Exception as e:
        import traceback
        print(f"Error fetching YouTube transcript: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)})

@app.route('/betting')
def betting_dashboard():
    """Betting dashboard with all players and filters"""
    # Get filter parameters
    market = request.args.get('market', 'win')
    sportsbook = request.args.get('sportsbook', '')  # New sportsbook filter
    min_ev = request.args.get('min_ev', '')
    max_ev = request.args.get('max_ev', '')
    sort_by = request.args.get('sort', 'adjusted_ev')
    sort_order = request.args.get('order', 'desc')
    
    # Connect to database
    conn = get_db_connection(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Print debug info about database tables
    print("Checking database tables...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row['name'] for row in cursor.fetchall()]
    print(f"Available tables: {tables}")
    
    if 'bet_recommendations' in tables:
        cursor.execute("SELECT COUNT(*) as count FROM bet_recommendations")
        count = cursor.fetchone()['count']
        print(f"Total bet recommendations: {count}")
        
        if count > 0:
            cursor.execute("SELECT DISTINCT event_name, market, sportsbook FROM bet_recommendations LIMIT 10")
            samples = cursor.fetchall()
            print("Sample data:")
            for sample in samples:
                print(f"  Event: {sample['event_name']}, Market: {sample['market']}, Sportsbook: {sample['sportsbook']}")
    
    # Get the latest event with recommendations
    cursor.execute("""
    SELECT event_name, MAX(timestamp) as latest
    FROM bet_recommendations
    GROUP BY event_name
    ORDER BY latest DESC
    LIMIT 1
    """)
    
    event_result = cursor.fetchone()
    
    if not event_result:
        print("No events found in bet_recommendations table")
        conn.close()
        return render_template('betting.html', event_name=None, 
                              market_data=None, last_updated=None,
                              available_markets=[], available_sportsbooks=[])
    
    event_name = event_result['event_name']
    last_updated = event_result['latest']
    print(f"Found event: {event_name}, last updated: {last_updated}")
    
    # Get available sportsbooks - FIX: Remove timestamp filter
    cursor.execute("""
    SELECT DISTINCT sportsbook 
    FROM bet_recommendations 
    WHERE event_name = ?
    ORDER BY sportsbook
    """, (event_name,))
    
    available_sportsbooks = [row['sportsbook'] for row in cursor.fetchall()]
    print(f"Available sportsbooks: {available_sportsbooks}")
    
    # Get available markets - FIX: Remove timestamp filter
    cursor.execute("""
    SELECT DISTINCT market 
    FROM bet_recommendations 
    WHERE event_name = ?
    ORDER BY market
    """, (event_name,))
    
    available_markets = [row['market'] for row in cursor.fetchall()]
    print(f"Available markets: {available_markets}")
    
    # FIX: Get the latest timestamp for the selected market
    cursor.execute("""
    SELECT MAX(timestamp) as latest_market_timestamp
    FROM bet_recommendations
    WHERE event_name = ? AND market = ?
    """, (event_name, market))
    
    latest_market_result = cursor.fetchone()
    if not latest_market_result or not latest_market_result['latest_market_timestamp']:
        print(f"No data found for market {market}")
        conn.close()
        return render_template('betting.html', event_name=event_name, 
                             market_data={"name": market, "display_name": format_market_name(market), "players": []}, 
                             available_markets=available_markets,
                             available_sportsbooks=available_sportsbooks,
                             selected_sportsbook=sportsbook,
                             last_updated=last_updated,
                             min_ev=min_ev, max_ev=max_ev,
                             sort_by=sort_by, sort_order=sort_order)
    
    # Build query for filtered odds data
    query = """
    SELECT r.*, p.name as player_name 
    FROM bet_recommendations r
    LEFT JOIN players p ON r.player_id = p.id
    WHERE r.event_name = ? AND r.market = ?
    """

    # Simplified parameter list - just the event name and market
    params = [event_name, market]

    # Add sportsbook filter if specified
    if sportsbook and sportsbook in available_sportsbooks:
        query += " AND r.sportsbook = ?"
        params.append(sportsbook)

    # Add EV filters if provided
    if min_ev and min_ev.replace('.', '', 1).isdigit():
        query += " AND r.adjusted_ev >= ?"
        params.append(float(min_ev))

    if max_ev and max_ev.replace('.', '', 1).isdigit():
        query += " AND r.adjusted_ev <= ?"
        params.append(float(max_ev))

    print(f"Query: {query}")
    print(f"Params: {params}")

    # Execute query
    cursor.execute(query, params)
    bet_data = cursor.fetchall()
    print(f"Retrieved {len(bet_data)} rows of bet data")
    
    # Group by player and find best sportsbook for each
    player_bets = {}

    for bet in bet_data:
        player_id = bet['player_id']

        model_probability = None
        try:
            model_probability = bet['model_probability']
        except (KeyError, IndexError):
            pass
        
        if player_id not in player_bets:
            player_bets[player_id] = {
                'player_id': player_id,
                'player_name': bet['player_name'] or 'Unknown Player',
                'mental_score': bet['mental_score'],
                'model_probability': model_probability,
                'best_bet': None,
                'all_bets': []
            }
        elif bet['player_name'] and player_bets[player_id]['player_name'] == 'Unknown Player':
            # Update player name if we find a better one
            player_bets[player_id]['player_name'] = bet['player_name']
        
        # Only add bets with valid decimal odds
        if bet['decimal_odds'] > 0:
            # Make a copy of the bet dictionary to avoid modifying the original
            bet_copy = dict(bet)
            
            # Ensure model_probability is included in the copied bet
            if 'model_probability' not in bet_copy and model_probability is not None:
                bet_copy['model_probability'] = model_probability
                
            player_bets[player_id]['all_bets'].append(bet_copy)
            
            # Update model_probability if not yet set and available in this bet
            if player_bets[player_id]['model_probability'] is None and model_probability is not None:
                player_bets[player_id]['model_probability'] = model_probability
            
            # Update best bet with priority on the selected sportsbook
            if sportsbook and bet['sportsbook'] == sportsbook:
                # If filtering by sportsbook, always use that sportsbook's odds
                player_bets[player_id]['best_bet'] = bet_copy
            elif player_bets[player_id]['best_bet'] is None or bet['adjusted_ev'] > player_bets[player_id]['best_bet']['adjusted_ev']:
                # Otherwise use the best EV
                player_bets[player_id]['best_bet'] = bet_copy
    
    # Convert to list
    player_list = list(player_bets.values())
    print(f"Processed {len(player_list)} unique players")
    
    # Sort based on selected criteria
    if sort_by == 'player_name':
        player_list.sort(key=lambda x: x['player_name'], reverse=(sort_order.lower() == 'desc'))
    elif sort_by == 'mental_score':
        player_list.sort(
            key=lambda x: x['mental_score'] if x['mental_score'] is not None else -999, 
            reverse=(sort_order.lower() == 'desc')
        )
    elif sort_by == 'decimal_odds':
        player_list.sort(
            key=lambda x: x['best_bet']['decimal_odds'] if x['best_bet'] else 0, 
            reverse=(sort_order.lower() != 'desc')  # Lower odds are better
        )
    else:
        # Default sort by adjusted EV
        player_list.sort(
            key=lambda x: x['best_bet']['adjusted_ev'] if x['best_bet'] else 0, 
            reverse=(sort_order.lower() == 'desc')
        )
    
    market_data = {
        'name': market,
        'display_name': format_market_name(market),
        'players': player_list
    }
    
    conn.close()
    
    return render_template('betting.html', 
                          event_name=event_name,
                          market_data=market_data, 
                          available_markets=available_markets,
                          available_sportsbooks=available_sportsbooks,
                          selected_sportsbook=sportsbook,
                          last_updated=last_updated,
                          min_ev=min_ev,
                          max_ev=max_ev,
                          sort_by=sort_by,
                          sort_order=sort_order)

@app.route('/betting/update', methods=['POST'])
def update_betting_recommendations():
    """Update betting recommendations"""
    try:
        print("Starting odds data update...")
        
        # Initialize OddsRetriever
        from odds_retriever import OddsRetriever
        odds_retriever = OddsRetriever(db_path=DB_PATH)
        
        print("OddsRetriever initialized")
        print(f"Database path: {DB_PATH}")
        print(f"API key available: {'Yes' if odds_retriever.api_key else 'No'}")
        
        # Update recommendations
        print("Calling update_odds_data()...")
        result = odds_retriever.update_odds_data()
        
        print(f"Update completed. Result keys: {list(result.keys() if result else [])}")
        
        if result and "event_name" in result:
            event_name = result["event_name"]
            print(f"Successfully updated data for event: {event_name}")
            
            # Count entries added
            market_counts = {}
            for market_name, market_data in result.get("markets", {}).items():
                market_counts[market_name] = len(market_data)
            
            print(f"Market data counts: {market_counts}")
            
            flash(f'Betting data updated successfully for {event_name}', 'success')
        else:
            print("No event data found to update")
            flash('No event data found to update', 'warning')
    except Exception as e:
        print(f"Error updating betting data: {str(e)}")
        flash(f'Error updating betting data: {str(e)}', 'error')
        import traceback
        traceback_str = traceback.format_exc()
        print(f"Full traceback:\n{traceback_str}")
    
    return redirect(url_for('betting_dashboard'))

@app.route('/betting/player/<int:player_id>')
def player_betting_detail(player_id):
    """Show betting recommendations for a specific player"""
    # Get filter parameter
    market = request.args.get('market', '')
    
    conn = get_db_connection(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get player info
    cursor.execute("""
    SELECT p.*, m.score as mental_score, m.justification
    FROM players p
    LEFT JOIN mental_form m ON p.id = m.player_id
    WHERE p.id = ?
    """, (player_id,))
    
    player = cursor.fetchone()
    
    if not player:
        conn.close()
        flash('Player not found!', 'error')
        return redirect(url_for('betting_dashboard'))
    
    # Get the latest event with recommendations for this player
    cursor.execute("""
    SELECT event_name, MAX(timestamp) as latest
    FROM bet_recommendations
    WHERE player_id = ?
    GROUP BY event_name
    ORDER BY latest DESC
    LIMIT 1
    """, (player_id,))
    
    event_result = cursor.fetchone()
    
    if not event_result:
        conn.close()
        return render_template('player_betting.html', player=player, 
                              market_groups=[], event_name=None,
                              selected_market=market,
                              available_markets=[])
    
    event_name = event_result['event_name']
    
    # Get all markets available for this player - FIX: remove timestamp filter
    cursor.execute("""
    SELECT DISTINCT market
    FROM bet_recommendations
    WHERE player_id = ? AND event_name = ?
    ORDER BY market
    """, (player_id, event_name))
    
    available_markets = [row['market'] for row in cursor.fetchall()]
    
    # FIX: For each market, get the latest timestamp and recommendations
    market_groups = {}
    
    # If a specific market is selected, only process that one
    markets_to_process = [market] if market and market in available_markets else available_markets
    
    for market_name in markets_to_process:
        # Get the latest timestamp for this market
        cursor.execute("""
        SELECT MAX(timestamp) as latest_market_timestamp
        FROM bet_recommendations
        WHERE player_id = ? AND event_name = ? AND market = ?
        """, (player_id, event_name, market_name))
        
        market_timestamp_result = cursor.fetchone()
        if not market_timestamp_result or not market_timestamp_result['latest_market_timestamp']:
            continue
            
        market_timestamp = market_timestamp_result['latest_market_timestamp']
        
        # Get recommendations for this market and timestamp
        cursor.execute("""
        SELECT *
        FROM bet_recommendations
        WHERE player_id = ? AND event_name = ? AND market = ? AND timestamp = ?
        ORDER BY adjusted_ev DESC
        """, (player_id, event_name, market_name, market_timestamp))
        
        recommendations = cursor.fetchall()
        
        if recommendations:
            market_groups[market_name] = {
                'name': market_name,
                'display_name': format_market_name(market_name),
                'recommendations': [dict(rec) for rec in recommendations]
            }
    
    # Convert to list and sort by market name
    market_list = list(market_groups.values())
    market_list.sort(key=lambda x: x['name'])
    
    # Get the most recent timestamp for display
    cursor.execute("""
    SELECT MAX(timestamp) as last_updated
    FROM bet_recommendations
    WHERE player_id = ? AND event_name = ?
    """, (player_id, event_name))
    
    last_updated_result = cursor.fetchone()
    last_updated = last_updated_result['last_updated'] if last_updated_result else None
    
    conn.close()
    
    return render_template('player_betting.html', 
                          player=player,
                          market_groups=market_list, 
                          event_name=event_name,
                          selected_market=market,
                          available_markets=available_markets,
                          last_updated=last_updated)

@app.route('/my-bets')
def my_bets():
    """View and manage bets"""
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    
    # Get pending bets
    cursor.execute('''
    SELECT * FROM bets
    WHERE outcome = 'pending'
    ORDER BY placed_date DESC
    ''')
    pending_bets = cursor.fetchall()
    
    # Get settled bets
    cursor.execute('''
    SELECT * FROM bets
    WHERE outcome != 'pending'
    ORDER BY settled_date DESC
    ''')
    settled_bets = cursor.fetchall()
    
    # Calculate stats
    stats = calculate_betting_stats(conn)
    
    conn.close()
    
    return render_template('my_bets.html', 
                          pending_bets=pending_bets,
                          settled_bets=settled_bets,
                          stats=stats)

@app.route('/track-bet', methods=['POST'])
def track_bet():
    """Record a new bet"""
    if request.method != 'POST':
        return redirect(url_for('my_bets'))
    
    # Get form data
    player_id = request.form.get('player_id')
    player_name = request.form.get('player_name')
    market = request.form.get('market')
    sportsbook = request.form.get('sportsbook')
    
    # Handle numeric fields with proper error handling
    try:
        odds = float(request.form.get('odds')) if request.form.get('odds') else 0
        stake = float(request.form.get('stake')) if request.form.get('stake') else 0
        base_ev = float(request.form.get('base_ev')) if request.form.get('base_ev') else 0
        mental_adjustment = float(request.form.get('mental_adjustment')) if request.form.get('mental_adjustment') else 0
        adjusted_ev = float(request.form.get('adjusted_ev')) if request.form.get('adjusted_ev') else 0
        base_probability = float(request.form.get('base_probability')) if request.form.get('base_probability') else 0
        
        # Handle the mental_score - be very careful with 'None' string
        mental_score_raw = request.form.get('mental_score')
        if mental_score_raw and mental_score_raw.lower() != 'none':
            mental_score = float(mental_score_raw)
        else:
            mental_score = None
    except ValueError as e:
        flash(f'Error converting form data: {str(e)}. Please check the values and try again.', 'error')
        return redirect(url_for('betting_dashboard'))
    
    event_name = request.form.get('event_name')
    notes = request.form.get('notes')
    
    # Calculate potential return
    potential_return = stake * odds
    
    # Calculate adjusted probability
    if base_probability > 0 and mental_adjustment is not None:
        adjustment_factor = 1 + (mental_adjustment / 100)
        adjusted_probability = base_probability * adjustment_factor
    else:
        adjusted_probability = base_probability
    
    # Book implied probability (based on odds)
    book_implied_probability = (1 / odds) * 100 if odds > 0 else 0
    
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    
    # Record the bet
    cursor.execute('''
    INSERT INTO bets (
        event_id, event_name, bet_type, bet_market, player_id, player_name,
        odds, stake, potential_return, placed_date, outcome,
        base_model_probability, mental_form_score, mental_adjustment,
        adjusted_probability, book_implied_probability, expected_value,
        notes, sportsbook
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        'current', event_name, 'outright', market, player_id, player_name,
        odds, stake, potential_return, datetime.now(), 'pending',
        base_probability, mental_score, mental_adjustment,
        adjusted_probability, book_implied_probability, adjusted_ev,
        notes, sportsbook
    ))
    
    conn.commit()
    conn.close()
    
    flash(f'Bet on {player_name} ({market}) has been tracked successfully', 'success')
    return redirect(url_for('my_bets'))

@app.route('/settle-bet', methods=['POST'])
def settle_bet():
    """Mark a bet as won, lost, or void"""
    if request.method != 'POST':
        return redirect(url_for('my_bets'))
        
    bet_id = request.form.get('bet_id')
    outcome = request.form.get('outcome')
    
    if not bet_id or not outcome or outcome not in ['win', 'loss', 'void']:
        flash('Invalid bet settlement data', 'error')
        return redirect(url_for('my_bets'))
    
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    
    # Get bet details
    cursor.execute('SELECT stake, odds, player_name, bet_market FROM bets WHERE bet_id = ?', (bet_id,))
    bet = cursor.fetchone()
    
    if not bet:
        conn.close()
        flash('Bet not found', 'error')
        return redirect(url_for('my_bets'))
    
    stake = bet['stake']
    odds = bet['odds']
    player_name = bet['player_name']
    market = bet['bet_market']
    
    # Calculate profit/loss
    if outcome == 'win':
        profit_loss = stake * (odds - 1)
    elif outcome == 'loss':
        profit_loss = -stake
    else:  # void
        profit_loss = 0
    
    # Update the bet
    cursor.execute('''
    UPDATE bets 
    SET outcome = ?, settled_date = ?, profit_loss = ?
    WHERE bet_id = ?
    ''', (outcome, datetime.now(), profit_loss, bet_id))
    
    conn.commit()
    conn.close()
    
    # Show appropriate message
    if outcome == 'win':
        flash(f'Bet on {player_name} marked as won! Profit: ${profit_loss:.2f}', 'success')
    elif outcome == 'loss':
        flash(f'Bet on {player_name} marked as lost. Loss: ${abs(profit_loss):.2f}', 'danger')
    else:
        flash(f'Bet on {player_name} marked as void.', 'info')
    
    return redirect(url_for('my_bets'))

@app.route('/update-bankroll', methods=['POST'])
def update_bankroll():
    """Update the current bankroll"""
    if request.method != 'POST':
        return redirect(url_for('my_bets'))
        
    new_bankroll = float(request.form.get('bankroll', 0))
    
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    
    # Get the latest performance metric
    cursor.execute('SELECT * FROM performance_metrics ORDER BY date DESC LIMIT 1')
    latest = cursor.fetchone()
    
    # Calculate metrics
    cursor.execute('''
    SELECT 
        COUNT(*) as total_bets,
        SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as winning_bets,
        SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losing_bets,
        SUM(CASE WHEN outcome = 'pending' THEN 1 ELSE 0 END) as pending_bets,
        SUM(stake) as total_staked,
        SUM(CASE WHEN outcome = 'win' THEN potential_return ELSE 0 END) as total_returns,
        SUM(CASE WHEN outcome != 'pending' THEN profit_loss ELSE 0 END) as profit_loss
    FROM bets
    ''')
    
    metrics = cursor.fetchone()
    
    # Insert new performance metrics
    if metrics:
        total_bets = metrics['total_bets'] or 0
        winning_bets = metrics['winning_bets'] or 0
        losing_bets = metrics['losing_bets'] or 0
        pending_bets = metrics['pending_bets'] or 0
        total_staked = metrics['total_staked'] or 0
        total_returns = metrics['total_returns'] or 0
        profit_loss = metrics['profit_loss'] or 0
        
        # Calculate ROI
        roi = (profit_loss / total_staked) * 100 if total_staked > 0 else 0
        
        cursor.execute('''
        INSERT INTO performance_metrics (
            date, total_bets, winning_bets, losing_bets, pending_bets,
            total_staked, total_returns, profit_loss, roi, current_bankroll
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now(), total_bets, winning_bets, losing_bets, pending_bets,
            total_staked, total_returns, profit_loss, roi, new_bankroll
        ))
    
    conn.commit()
    conn.close()
    
    flash(f'Bankroll updated to ${new_bankroll:.2f}', 'success')
    return redirect(url_for('my_bets'))

def calculate_betting_stats(conn):
    """Calculate betting statistics for display"""
    cursor = conn.cursor()
    
    # Get overall counts
    cursor.execute('''
    SELECT 
        COUNT(*) as total_bets,
        SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as winning_bets,
        SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losing_bets,
        SUM(CASE WHEN outcome != 'pending' THEN 1 ELSE 0 END) as total_settled_bets,
        SUM(stake) as total_staked,
        SUM(CASE WHEN outcome = 'win' THEN potential_return ELSE 0 END) as total_returns,
        SUM(CASE WHEN outcome != 'pending' THEN profit_loss ELSE 0 END) as total_profit_loss
    FROM bets
    ''')
    
    overall = cursor.fetchone()
    
    # Initialize with default values in case no bets exist
    win_rate = 0
    roi = 0
    total_settled_bets = 0
    winning_bets = 0
    losing_bets = 0
    total_staked = 0
    total_profit_loss = 0
    
    # Only calculate stats if we have overall data
    if overall:
        # Make sure values are not None - use 0 as default
        winning_bets = overall['winning_bets'] or 0
        losing_bets = overall['losing_bets'] or 0
        total_settled_bets = overall['total_settled_bets'] or 0
        total_staked = overall['total_staked'] or 0
        total_profit_loss = overall['total_profit_loss'] or 0
        
        # Calculate win rate and ROI
        win_rate = winning_bets / total_settled_bets if total_settled_bets > 0 else 0
        roi = (total_profit_loss / total_staked) * 100 if total_staked > 0 else 0
    
    # Get the latest bankroll
    cursor.execute('SELECT current_bankroll FROM performance_metrics ORDER BY date DESC LIMIT 1')
    bankroll_row = cursor.fetchone()
    current_bankroll = bankroll_row['current_bankroll'] if bankroll_row else 1000  # Default starting bankroll
    
    # Performance by market
    cursor.execute('''
    SELECT 
        bet_market as market,
        COUNT(*) as count,
        SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN outcome != 'pending' THEN profit_loss ELSE 0 END) as profit_loss,
        SUM(CASE WHEN outcome != 'pending' THEN stake ELSE 0 END) as total_staked
    FROM bets
    WHERE outcome != 'pending'
    GROUP BY bet_market
    ''')
    
    market_rows = cursor.fetchall()
    market_breakdown = []
    
    for market in market_rows:
        market_win_rate = market['wins'] / market['count'] if market['count'] > 0 else 0
        market_roi = (market['profit_loss'] / market['total_staked']) * 100 if market['total_staked'] > 0 else 0
        
        market_breakdown.append({
            'name': market['market'],
            'count': market['count'],
            'win_rate': market_win_rate,
            'profit_loss': market['profit_loss'] or 0,
            'roi': market_roi
        })
    
    # Performance by sportsbook
    cursor.execute('''
    SELECT 
        sportsbook,
        COUNT(*) as count,
        SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN outcome != 'pending' THEN profit_loss ELSE 0 END) as profit_loss,
        SUM(CASE WHEN outcome != 'pending' THEN stake ELSE 0 END) as total_staked
    FROM bets
    WHERE outcome != 'pending'
    GROUP BY sportsbook
    ''')
    
    sportsbook_rows = cursor.fetchall()
    sportsbook_breakdown = []
    
    for book in sportsbook_rows:
        book_win_rate = book['wins'] / book['count'] if book['count'] > 0 else 0
        book_roi = (book['profit_loss'] / book['total_staked']) * 100 if book['total_staked'] > 0 else 0
        
        sportsbook_breakdown.append({
            'name': book['sportsbook'] or 'Unknown',
            'count': book['count'],
            'win_rate': book_win_rate,
            'profit_loss': book['profit_loss'] or 0,
            'roi': book_roi
        })
    
    # Performance by EV range - only run this query if we have settled bets
    ev_breakdown = []
    if total_settled_bets > 0:
        try:
            cursor.execute('''
            SELECT 
                CASE
                    WHEN expected_value < 0 THEN 'Negative'
                    WHEN expected_value < 5 THEN '0-5%'
                    WHEN expected_value < 10 THEN '5-10%'
                    WHEN expected_value < 20 THEN '10-20%'
                    ELSE '20%+'
                END as ev_range,
                COUNT(*) as count,
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome != 'pending' THEN profit_loss ELSE 0 END) as profit_loss,
                SUM(CASE WHEN outcome != 'pending' THEN stake ELSE 0 END) as total_staked
            FROM bets
            WHERE outcome != 'pending'
            GROUP BY ev_range
            ORDER BY MIN(expected_value)
            ''')
            
            ev_rows = cursor.fetchall()
            
            for ev in ev_rows:
                ev_win_rate = ev['wins'] / ev['count'] if ev['count'] > 0 else 0
                ev_roi = (ev['profit_loss'] / ev['total_staked']) * 100 if ev['total_staked'] > 0 else 0
                
                ev_breakdown.append({
                    'name': ev['ev_range'],
                    'count': ev['count'],
                    'win_rate': ev_win_rate,
                    'profit_loss': ev['profit_loss'] or 0,
                    'roi': ev_roi
                })
        except Exception as e:
            print(f"Error processing EV breakdown: {e}")
    
    # Performance by mental form range - only run this query if we have settled bets
    mental_form_breakdown = []
    if total_settled_bets > 0:
        try:
            cursor.execute('''
            SELECT 
                CASE
                    WHEN mental_form_score <= -0.5 THEN 'Strong Negative'
                    WHEN mental_form_score <= -0.2 THEN 'Moderate Negative'
                    WHEN mental_form_score < 0.2 THEN 'Neutral'
                    WHEN mental_form_score < 0.5 THEN 'Moderate Positive'
                    WHEN mental_form_score IS NOT NULL THEN 'Strong Positive'
                    ELSE 'Unknown'
                END as mental_form_range,
                COUNT(*) as count,
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN outcome != 'pending' THEN profit_loss ELSE 0 END) as profit_loss,
                SUM(CASE WHEN outcome != 'pending' THEN stake ELSE 0 END) as total_staked
            FROM bets
            WHERE outcome != 'pending'
            GROUP BY mental_form_range
            ORDER BY MIN(mental_form_score)
            ''')
            
            mental_form_rows = cursor.fetchall()
            
            for mf in mental_form_rows:
                mf_win_rate = mf['wins'] / mf['count'] if mf['count'] > 0 else 0
                mf_roi = (mf['profit_loss'] / mf['total_staked']) * 100 if mf['total_staked'] > 0 else 0
                
                mental_form_breakdown.append({
                    'name': mf['mental_form_range'],
                    'count': mf['count'],
                    'win_rate': mf_win_rate,
                    'profit_loss': mf['profit_loss'] or 0,
                    'roi': mf_roi
                })
        except Exception as e:
            print(f"Error processing mental form breakdown: {e}")
    
    # Return all the stats
    return {
        'total_bets': overall['total_bets'] if overall else 0,
        'winning_bets': winning_bets,
        'losing_bets': losing_bets,
        'total_settled_bets': total_settled_bets,
        'total_staked': total_staked,
        'total_returns': overall['total_returns'] if overall and overall['total_returns'] is not None else 0,
        'total_profit_loss': total_profit_loss,
        'win_rate': win_rate,
        'roi': roi,
        'current_bankroll': current_bankroll,
        'market_breakdown': market_breakdown,
        'sportsbook_breakdown': sportsbook_breakdown,
        'ev_breakdown': ev_breakdown,
        'mental_form_breakdown': mental_form_breakdown
    }

@app.route('/delete-bet', methods=['POST'])
def delete_bet():
    """Delete a bet completely"""
    if request.method != 'POST':
        return redirect(url_for('my_bets'))
        
    bet_id = request.form.get('bet_id')
    
    if not bet_id:
        flash('Invalid bet data', 'error')
        return redirect(url_for('my_bets'))
    
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    
    # Get bet details for the flash message
    cursor.execute('SELECT player_name, bet_market FROM bets WHERE bet_id = ?', (bet_id,))
    bet = cursor.fetchone()
    
    if not bet:
        conn.close()
        flash('Bet not found', 'error')
        return redirect(url_for('my_bets'))
    
    player_name = bet['player_name']
    market = bet['bet_market']
    
    # Delete the bet
    cursor.execute('DELETE FROM bets WHERE bet_id = ?', (bet_id,))
    
    conn.commit()
    conn.close()
    
    flash(f'Bet on {player_name} ({market}) has been deleted', 'success')
    return redirect(url_for('my_bets'))

@app.route('/about')
def about():
    """About page with system information"""
    return render_template('about.html')

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(debug=True)