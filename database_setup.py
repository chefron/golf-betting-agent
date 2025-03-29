"""
Database setup module for golf mental form analysis.

This module creates the SQLite database structure for storing
player information, insights, and mental form scores.
"""

import sqlite3
import os

def create_database(db_path="data/db/mental_form.db"):
    """Create the initial database schema"""
    # Create directories if they don't exist
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Players table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS players (
        id INTEGER PRIMARY KEY,
        dg_id INTEGER UNIQUE,
        name TEXT NOT NULL,
        amateur INTEGER DEFAULT 0,
        country TEXT,
        country_code TEXT,
        nicknames TEXT,
        notes TEXT
    )
    ''')

    # Insights table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS insights (
        id INTEGER PRIMARY KEY,
        player_id INTEGER,
        text TEXT NOT NULL,
        source TEXT,
        source_type TEXT,
        content_title TEXT,  
        content_url TEXT,    
        date TEXT,
        FOREIGN KEY (player_id) REFERENCES players (id)
    )
    ''')

    # Add index on player_id for better performance
    cursor.execute('''
    CREATE INDEX IF NOT EXISTS idx_insights_player_id ON insights(player_id)
    ''')
    
    # Mental form table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS mental_form (
        id INTEGER PRIMARY KEY,
        player_id INTEGER UNIQUE,
        score REAL,
        justification TEXT,
        last_updated TEXT,
        FOREIGN KEY (player_id) REFERENCES players (id)
    )
    ''')
    
    # Mental form history table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS mental_form_history (
        id INTEGER PRIMARY KEY,
        player_id INTEGER,
        score REAL,
        date TEXT,
        insights_count INTEGER,
        FOREIGN KEY (player_id) REFERENCES players (id)
    )
    ''')

    # Odds table - stores raw odds data
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS odds (
        id INTEGER PRIMARY KEY,
        player_id INTEGER,
        dg_id INTEGER,
        event_name TEXT,
        market TEXT,
        sportsbook TEXT,
        decimal_odds REAL,
        model_probability REAL,
        model_used TEXT,
        timestamp TEXT,
        FOREIGN KEY (player_id) REFERENCES players (id)
    )
    ''')

    # Betting recommendations table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bet_recommendations (
        id INTEGER PRIMARY KEY,
        player_id INTEGER,
        event_name TEXT,
        market TEXT,
        sportsbook TEXT,
        decimal_odds REAL,
        base_ev REAL,
        mental_adjustment REAL,
        adjusted_ev REAL,
        mental_score REAL,
        timestamp TEXT,
        FOREIGN KEY (player_id) REFERENCES players (id)
    )
    ''')
    
    conn.commit()
    conn.close()
    
    print(f"Database created at {db_path}")
    return db_path

if __name__ == "__main__":
    create_database()