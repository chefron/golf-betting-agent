from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import os
import sys
from datetime import datetime

# Add parent directory to path to find the modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import your existing database utility functions
from db_utils import (
    get_db_connection, 
    add_insight, 
    calculate_mental_form, 
    get_player_by_name,
    search_players
)

# Import insight extraction functionality
from insights_extractor import create_claude_prompt, query_claude, parse_claude_response

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev_key_for_testing")

# Default database path - resolves to the correct location from the web directory
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data/db/mental_form.db")

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
    SELECT p.name, m.score 
    FROM mental_form m
    JOIN players p ON m.player_id = p.id
    ORDER BY m.score DESC
    LIMIT 5
    """)
    top_players = cursor.fetchall()

    # Get bottom 5 players by mental form score
    cursor.execute("""
    SELECT p.name, m.score 
    FROM mental_form m
    JOIN players p ON m.player_id = p.id
    ORDER BY m.score ASC
    LIMIT 5
    """)
    bottom_players = cursor.fetchall()

    # Get recently updated players
    cursor.execute("""
    SELECT p.name, m.score, m.last_updated
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
    return render_template('index.html', stats=stats)

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
    query += " LIMIT 200"

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
        score, justification = calculate_mental_form(player_id)
        flash(f'Mental form recalculated: {score}', 'success')
    except Exception as e:
        flash(f'Error calculating mental form: {str(e)}', 'error')
    
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
        players = get_player_by_name(player_name)
        conn.close()

        if not players:
            flash(f'Player not found: {player_name}', 'error')
            return redirect(url_for('add_new_insight'))
        
        player_id = players[0]['id']

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
                
                # Try to find the player in the database
                player = get_player_by_name(player_name)
                
                insight_data = {
                    'player_name': player_name,
                    'text': insight_text,
                    'matched': False,
                    'player_id': None
                }
                
                if player:
                    # Add insight
                    player_id = player[0]["id"]
                    add_insight(
                        player_id=player_id,
                        text=insight_text,
                        source=source,
                        source_type="podcast",
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