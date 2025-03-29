from flask import Flask, render_template, request, redirect, url_for, flash
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
    
    return render_template('add_insight.html', sources=sources, source_types=source_types, 
                          today=datetime.now().strftime("%Y-%m-%d"))

@app.route('/edit_insight/<int:insight_id>', methods=['GET', 'POST'])
def edit_insight(insight_id):
    """Edit an existing insight"""
    conn = get_db_connection(DB_PATH)
    cursor = conn.cursor()
    
    if request.method == 'POST':
        text = request.form.get('text')
        source = request.form.get('source')
        source_type = request.form.get('source_type')
        content_title = request.form.get('content_title', '')
        content_url = request.form.get('content_url', '')
        date = request.form.get('date')
        
        # Update the insight
        cursor.execute("""
        UPDATE insights
        SET text = ?, source = ?, source_type = ?, content_title = ?, content_url = ?, date = ?
        WHERE id = ?
        """, (text, source, source_type, content_title, content_url, date, insight_id))
        
        # Get player_id for redirect
        cursor.execute("SELECT player_id FROM insights WHERE id = ?", (insight_id,))
        player_id = cursor.fetchone()[0]
        
        # Mark mental form for recalculation
        cursor.execute("""
        UPDATE mental_form
        SET last_updated = NULL
        WHERE player_id = ?
        """, (player_id,))
        
        conn.commit()
        conn.close()
        
        flash('Insight updated successfully', 'success')
        return redirect(url_for('player_detail', player_id=player_id))
    
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
                        date=datetime.now().strftime("%Y-%m-%d")
                    )
                    insight_data['matched'] = True
                    insight_data['player_id'] = player_id
                
                extracted_insights.append(insight_data)
            
            conn.close()
            
            return render_template('process_results.html', 
                                 insights=extracted_insights,
                                 event_name=event_name,
                                 source=source)
                
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
    
    return render_template('process.html', sources=sources)

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
    JOIN (
        SELECT player_id, market, MAX(timestamp) as max_time
        FROM bet_recommendations
        WHERE event_name = ? AND market = ?
        GROUP BY player_id, market
    ) latest ON r.player_id = latest.player_id AND r.market = latest.market AND r.timestamp = latest.max_time
    LEFT JOIN players p ON r.player_id = p.id
    """

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
    # If sportsbook filter is active, only include those odds
    player_bets = {}
    
    for bet in bet_data:
        player_id = bet['player_id']
        
        if player_id not in player_bets:
            player_bets[player_id] = {
                'player_id': player_id,
                'player_name': bet['player_name'] or 'Unknown Player',
                'mental_score': bet['mental_score'],
                'best_bet': None,
                'all_bets': []
            }
        
        player_bets[player_id]['all_bets'].append(dict(bet))
        
        # Update best bet if this is better or if we're filtering by a specific sportsbook
        if (player_bets[player_id]['best_bet'] is None or 
            bet['adjusted_ev'] > player_bets[player_id]['best_bet']['adjusted_ev'] or
            (sportsbook and bet['sportsbook'] == sportsbook)):
            player_bets[player_id]['best_bet'] = dict(bet)
    
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