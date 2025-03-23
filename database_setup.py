"""
Database setup module for golf sentiment analysis.

This module creates the SQLite database structure for storing
player information, insights, and sentiment scores.
"""

import sqlite3
import os

def create_database(db_path="data/db/sentiment.db"):
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
        notes TEXT,
        manual_adjustment REAL DEFAULT 0
    )
    ''')
    
    # Insights table - with more generic content fields
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
    
    # Sentiment table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sentiment (
        id INTEGER PRIMARY KEY,
        player_id INTEGER UNIQUE,
        score REAL,
        last_updated TEXT,
        FOREIGN KEY (player_id) REFERENCES players (id)
    )
    ''')
    
    # Sentiment history table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sentiment_history (
        id INTEGER PRIMARY KEY,
        player_id INTEGER,
        score REAL,
        date TEXT,
        insights_count INTEGER,
        FOREIGN KEY (player_id) REFERENCES players (id)
    )
    ''')
    
    conn.commit()
    conn.close()
    
    print(f"Database created at {db_path}")
    return db_path

if __name__ == "__main__":
    create_database()