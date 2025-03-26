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