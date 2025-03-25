"""
Database utility functions for the golf sentiment analysis system.

This module provides functions for working with the sentiment database,
including adding insights, calculating sentiment scores, and querying data.
"""

import sqlite3
import datetime
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

def get_db_connection(db_path="data/db/sentiment.db"):
    """Get a connection to the database."""
    conn = sqlite3.connect(db_path)
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
    
    # Set sentiment last_updated to NULL to trigger recalculation
    cursor.execute('''
    UPDATE sentiment
    SET last_updated = NULL
    WHERE player_id = ?
    ''', (player_id,))
    
    conn.commit()
    conn.close()
    
    return insight_id

def calculate_sentiment(player_id, max_insights=20):
    """
    Calculate sentiment score for a player based on their insights.
    
    Args:
        player_id: ID of the player in the database
        max_insights: Maximum number of insights to use (most recent)
        
    Returns:
        Calculated sentiment score
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
        return 0  # Neutral sentiment if no insights
    
    # Use anthropic to calculate sentiment
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("Anthropic API key is required but not found in environment variables")
    
    client = anthropic.Anthropic(api_key=api_key)
    
    # Prepare insights for prompt
    insights_text = "\n\n".join([f"Date: {i['date']}\nInsight: {i['text']}" for i in insights])
    
    # Create the prompt
    prompt = f"""
    Based on the following {len(insights)} insights about golfer {player_name}, assess their current MENTAL FORM on a scale from -1 to 1. This represents qualitative factors that traditional statistical models cannot capture.

    -1 = Severely compromised mental state (likely to significantly underperform statistical expectations)
    0 = Neutral mental state (performing in line with statistical expectations)
    1 = Exceptional mental state (likely to significantly outperform statistical expectations)

    MENTAL FORM ASSESSMENT FRAMEWORK:

    1. Emotional Regulation
    - NEGATIVE: On-course emotional outbursts (club throwing/breaking, visible anger), inability to move past mistakes
    - POSITIVE: Demonstrated resilience after setbacks, calm demeanor under pressure

    2. Confidence Level
    - NEGATIVE: Self-doubt in interviews, tentative decision-making, defensive language about game
    - POSITIVE: Expressed belief in abilities, aggressive strategy choices, positive self-talk

    3. Focus & Concentration
    - NEGATIVE: Distracted by external factors, inconsistent pre-shot routines, rushing shots
    - POSITIVE: Enhanced visualization techniques, improved shot commitment, present-focused mindset

    4. Life Stability
    - NEGATIVE: Personal difficulties (family issues, controversies), major life adjustments (new child, moving locations)
    - POSITIVE: Resolution of off-course distractions, improved work-life balance

    5. Support System
    - NEGATIVE: Caddie/coach conflicts, frequent team changes, isolation from support network
    - POSITIVE: Strong team chemistry, productive coaching relationships, positive influence from mentors

    6. Physical Readiness
    - NEGATIVE: Unreported injuries, fatigue from scheduling, uncomfortable equipment changes
    - POSITIVE: Enhanced fitness regimen, proper recovery protocols, optimal equipment setup

    7. Course Management
    - NEGATIVE: Poor decision-making patterns, failure to adapt to conditions
    - POSITIVE: Strategic improvements, better risk assessment, course-specific preparation

    8. Performance Trends
    - NEGATIVE: Pattern of late-round collapses, difficulty closing tournaments
    - POSITIVE: Clutch performances, improvement in pressure situations, momentum from recent success

    WEIGHTING INSTRUCTIONS:
    - Recent insights (within past 2 weeks) should carry more weight than older ones
    - Observable behaviors should outweigh speculative commentary
    - Do not double-count redundant insights

    Here are the insights:
    {insights_text}

    Based solely on these insights and the framework above, provide your mental form score as a single number between -1 and 1, with no additional text.
    """
    
    # Call Claude to analyze sentiment
    response = client.messages.create(
        model="claude-3-7-sonnet-20250219",
        max_tokens=500,
        temperature=0,
        system="You are an expert in qualitative golf analysis, specializing in identifying the non-statistical factors that influence player performance. Your task is to evaluate insights about golfers and determine how the qualitative factors mentioned might cause a player to perform differently than pure statistics would predict. When asked to provide a sentiment score, you will respond with ONLY a single number on the specified scale, with no explanation or additional text.",
        messages=[{"role": "user", "content": prompt}]
    )
    
    # Extract sentiment score from response
    full_response = response.content[0].text.strip()
    
    # Always print the full response
    print(f"Sentiment analysis for {player_name}:")
    print(f"Full response: '{full_response}'")
    
    try:
        # Try to parse as a float
        sentiment_score = float(full_response)
        
        # Ensure score is in valid range
        sentiment_score = max(-1, min(1, sentiment_score))
        
        print(f"Parsed sentiment score: {sentiment_score}")
    except (ValueError, IndexError):
        print(f"Error parsing sentiment score. Using default neutral value (0).")
        sentiment_score = 0
    
    # Update sentiment in database
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Check if sentiment record exists
    cursor.execute('SELECT id FROM sentiment WHERE player_id = ?', (player_id,))
    sentiment_record = cursor.fetchone()
    
    if sentiment_record:
        # Update existing record
        cursor.execute('''
        UPDATE sentiment
        SET score = ?, last_updated = ?
        WHERE player_id = ?
        ''', (sentiment_score, now, player_id))
    else:
        # Create new record
        cursor.execute('''
        INSERT INTO sentiment (player_id, score, last_updated)
        VALUES (?, ?, ?)
        ''', (player_id, sentiment_score, now))
    
    # Add to sentiment history
    cursor.execute('''
    INSERT INTO sentiment_history (player_id, score, date, insights_count)
    VALUES (?, ?, ?, ?)
    ''', (player_id, sentiment_score, now, len(insights)))
    
    conn.commit()
    conn.close()
    
    return sentiment_score

def get_player_by_name(name, fuzzy=True):
    """
    Get player by name, with optional fuzzy matching.
    
    Args:
        name: Player name to search for
        fuzzy: If True, allow partial matches
        
    Returns:
        Player record or None if not found
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if fuzzy:
        # Case-insensitive partial match
        cursor.execute('''
        SELECT * FROM players 
        WHERE LOWER(name) LIKE LOWER(?)
        ''', (f'%{name}%',))
    else:
        # Exact match
        cursor.execute('''
        SELECT * FROM players 
        WHERE LOWER(name) = LOWER(?)
        ''', (name,))
    
    players = cursor.fetchall()
    conn.close()
    
    return players

def get_players_by_sentiment(min_score=0.3, max_players=20):
    """
    Get players with high sentiment scores.
    
    Args:
        min_score: Minimum sentiment score
        max_players: Maximum number of players to return
        
    Returns:
        List of players with high sentiment
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT p.id, p.name, p.dg_id, p.manual_adjustment, s.score, s.last_updated
    FROM players p
    JOIN sentiment s ON p.id = s.player_id
    WHERE s.score >= ?
    ORDER BY s.score DESC
    LIMIT ?
    ''', (min_score, max_players))
    
    players = cursor.fetchall()
    conn.close()
    
    return players