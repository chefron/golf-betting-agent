"""
Database utility functions for the golf mental form analysis system.

This module provides functions for working with the mental form database,
including adding insights, calculating  scores, and querying data.
"""

import sqlite3
import datetime
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

def get_db_connection(db_path="data/db/mental_form.db"):
    """Get a connection to the database."""
    # Always use absolute path for consistency
    abs_path = "/home/chefron/CAPTCHA/golf-betting-agent/data/db/mental_form.db"
    
    print(f"Connecting to database at: {abs_path}")
    print(f"File exists: {os.path.exists(abs_path)}")
    print(f"Current directory: {os.getcwd()}")
    
    conn = sqlite3.connect(abs_path)
    conn.row_factory = sqlite3.Row  # This enables column access by name
    return conn

def add_insight(player_id, text, source, source_type, content_title="", content_url="", date=None):
    """
    Add a new insight for a player.
    
    Args:
        player_id: ID of the player in the database
        text: The insight text
        source: Source of the insight (podcast name, website, etc.)
        source_type: Type of source (podcast, article, tweet, etc.)
        content_title: Title of the content
        content_url: URL to the original content
        date: Date of the insight (defaults to current date)
        
    Returns:
        ID of the new insight
    """
    if date is None:
        date = datetime.datetime.now().strftime("%Y-%m-%d")
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO insights 
    (player_id, text, source, source_type, content_title, content_url, date)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (player_id, text, source, source_type, content_title, content_url, date))
    
    insight_id = cursor.lastrowid
    
    # Set mental_form last_updated to NULL to trigger recalculation
    cursor.execute('''
    UPDATE mental_form
    SET last_updated = NULL
    WHERE player_id = ?
    ''', (player_id,))
    
    conn.commit()
    conn.close()
    
    return insight_id

def calculate_mental_form(player_id, max_insights=20):
    """
    Calculate mental form score for a player based on their insights.
    
    Args:
        player_id: ID of the player in the database
        max_insights: Maximum number of insights to use (most recent)
        
    Returns:
        Calculated mental form score, justification text
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get player name
    cursor.execute('SELECT name FROM players WHERE id = ?', (player_id,))
    player = cursor.fetchone()
    if not player:
        conn.close()
        raise ValueError(f"Player with ID {player_id} not found")
    
    player_name = player['name']
    
    # Get the most recent insights
    cursor.execute('''
    SELECT text, date
    FROM insights
    WHERE player_id = ?
    ORDER BY date DESC
    LIMIT ?
    ''', (player_id, max_insights))
    
    insights = cursor.fetchall()
    
    if not insights:
        conn.close()
        return 0, "No insights available for assessment."  # Neutral mental form if no insights
    
    # Use anthropic to calculate mental form
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("Anthropic API key is required but not found in environment variables")
    
    client = anthropic.Anthropic(api_key=api_key)

    # Get current date for context
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # Prepare insights for prompt
    insights_text = "\n\n".join([f"Date: {i['date']}\nInsight: {i['text']}" for i in insights])
    
    # Create the prompt
    prompt = f"""
    Based on the following {len(insights)} insights about golfer {player_name}, assess their current MENTAL FORM on a scale from -1 to 1. This represents qualitative factors that traditional statistical models cannot capture.

    -1 = Severely compromised mental state (likely to significantly underperform statistical expectations)
    0 = Neutral mental state (performing in line with statistical expectations)
    1 = Exceptional mental state (likely to significantly outperform statistical expectations)

    Today's date: {today}

    MENTAL FORM ASSESSMENT FRAMEWORK:

    1. Emotional Regulation
    - NEGATIVE: On-course emotional outbursts, visible frustration, inability to move past mistakes
    - POSITIVE: Demonstrated resilience, calm demeanor, constructive response to challenges

    2. Confidence Level
    - NEGATIVE: Expressed self-doubt, hesitancy in decision-making, defensive language
    - POSITIVE: Stated belief in abilities, decisive approach, positive self-talk

    3. Focus & Concentration
    - NEGATIVE: Mentioned distractions, disrupted routines, rushing process
    - POSITIVE: Discussed improved mental clarity, enhanced preparation, present-focused mindset

    4. Life Stability
    - NEGATIVE: Personal difficulties, major life adjustments, reported off-course stress
    - POSITIVE: Expressed contentment with life balance, resolution of previous distractions

    5. Support System
    - NEGATIVE: Team conflicts, coaching/caddie changes, isolation concerns
    - POSITIVE: Mentioned positive team dynamics, valuable mentor relationships

    6. Physical Well-being
    - NEGATIVE: Discussed injuries, fatigue, discomfort with equipment
    - POSITIVE: Reported improved fitness, effective recovery, equipment satisfaction

    7. Mental Approach
    - NEGATIVE: Described poor decision-making process, rigid strategic thinking
    - POSITIVE: Discussed improved perspective, adaptability, or strategic clarity

    SCORING GUIDELINES:
    - DO NOT infer current mental state from performance results alone
    - Positive (or negative) performances on the course DO NOT necessarily indicate a positive (or negative) mental state
    - The default assumption is 0 (neutral) - move away ONLY with explicit evidence
    - Insights older than 30 days should carry minimal weight
    - Scores beyond ±0.5 require substantial evidence across multiple categories
    - Do not double-count redundant insights (there will likely be redundancies!)

    Here are the insights:
    {insights_text}

    Based solely on these insights and the framework above:
    1. Provide a current mental form score between -1 and 1
    2. Explain your reasoning in 3-5 sentences, noting any clear trends in the player's mental state based on the timeline of insights. Your explanation must stand alone without referencing "insights" directly.

    Format your response as:
    SCORE: [number between -1 and 1]
    JUSTIFICATION: [your explanation and trend analysis]
    """
    
    # Call Claude to analyze mental form
    response = client.messages.create(
        model="claude-3-7-sonnet-20250219",
        max_tokens=1000,
        temperature=.5,
        system="You are an expert in qualitative golf analysis, specializing in identifying the non-statistical factors that influence player performance. Your task is to evaluate insights about golfers and determine how the qualitative factors mentioned might cause a player to perform differently than pure statistics would predict.",
        messages=[{"role": "user", "content": prompt}]
    )
    
    # Extract mental form score and justification from response
    full_response = response.content[0].text.strip()
    
    # Always print the full response
    print(f"Mental form analysis for {player_name}:")
    print(f"Full response: '{full_response}'")
    
    # Try to parse score and justification
    try:
        # Extract score
        score_line = [line for line in full_response.split('\n') if line.startswith('SCORE:')]
        if score_line:
            score_text = score_line[0].replace('SCORE:', '').strip()
            mental_form_score = float(score_text)
            # Ensure score is in valid range
            mental_form_score = max(-1, min(1, mental_form_score))
        else:
            raise ValueError("Score not found in response")
            
        # Extract justification
        justification_line = [line for line in full_response.split('\n') if line.startswith('JUSTIFICATION:')]
        if justification_line:
            # Get the justification text, which might span multiple lines
            justification_start_idx = full_response.find('JUSTIFICATION:')
            justification_text = full_response[justification_start_idx:].replace('JUSTIFICATION:', '').strip()
        else:
            justification_text = "No justification provided."
        
        print(f"Parsed mental form score: {mental_form_score}")
        print(f"Justification: {justification_text}")
    except (ValueError, IndexError) as e:
        print(f"Error parsing mental form data: {e}. Using default neutral value (0).")
        mental_form_score = 0
        justification_text = "Error parsing response."
    
    # Update mental_form in database
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Check if mental_form record exists
    cursor.execute('SELECT id FROM mental_form WHERE player_id = ?', (player_id,))
    record = cursor.fetchone()
    
    if record:
        # Update existing record
        cursor.execute('''
        UPDATE mental_form
        SET score = ?, justification = ?, last_updated = ?
        WHERE player_id = ?
        ''', (mental_form_score, justification_text, now, player_id))
    else:
        # Create new record
        cursor.execute('''
        INSERT INTO mental_form (player_id, score, justification, last_updated)
        VALUES (?, ?, ?, ?)
        ''', (player_id, mental_form_score, justification_text, now))
    
    # Add to mental_form_history
    cursor.execute('''
    INSERT INTO mental_form_history (player_id, score, date, insights_count)
    VALUES (?, ?, ?, ?)
    ''', (player_id, mental_form_score, now, len(insights)))
    
    conn.commit()
    conn.close()
    
    return mental_form_score, justification_text

def search_players(filters=None, order_by=None, limit=None):
    """
    Flexible search function for players with optional filtering.
    
    Args:
        filters: Dictionary of field:value pairs to filter on
                (e.g., {'mental_form.score__gte': 0.3} for score >= 0.3)
        order_by: Field to order by, with optional '-' prefix for descending
                 (e.g., '-mental_form.score' for highest scores first)
        limit: Maximum number of results to return
        
    Returns:
        List of matching player records
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Start with base query joining players and mental_form tables
    query = """
    SELECT p.id, p.name, p.dg_id, p.amateur, p.country, m.score, m.justification, m.last_updated
    FROM players p
    LEFT JOIN mental_form m ON p.id = m.player_id
    """
    
    # Add WHERE clauses for filters
    where_clauses = []
    params = []
    
    if filters:
        for key, value in filters.items():
            # Handle operators in field names (e.g., mental_form.score__gte)
            if '__' in key:
                field, operator = key.split('__')
                if operator == 'gt':
                    where_clauses.append(f"{field} > ?")
                elif operator == 'gte':
                    where_clauses.append(f"{field} >= ?")
                elif operator == 'lt':
                    where_clauses.append(f"{field} < ?")
                elif operator == 'lte':
                    where_clauses.append(f"{field} <= ?")
                elif operator == 'like':
                    where_clauses.append(f"{field} LIKE ?")
                    value = f"%{value}%"  # Add wildcards for LIKE
                else:
                    where_clauses.append(f"{field} = ?")
            else:
                where_clauses.append(f"{key} = ?")
            
            params.append(value)
    
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    
    # Add ORDER BY
    if order_by:
        if order_by.startswith('-'):
            query += f" ORDER BY {order_by[1:]} DESC"
        else:
            query += f" ORDER BY {order_by} ASC"
    
    # Add LIMIT
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    
    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()
    
    return results