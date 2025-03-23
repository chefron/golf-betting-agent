"""
Import players module for golf sentiment analysis.

This script imports player data from the Data Golf API into the local SQLite database.
"""

import requests
import sqlite3
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def import_players_from_datagolf(db_path="data/db/sentiment.db"):
    """Import all players from Data Golf API"""
    # Get API key from environment variable
    api_key = os.environ.get("DATAGOLF_API_KEY", "")
    if not api_key:
        print("Warning: No Data Golf API key found. Using default key.")
        api_key = "6e301f31eb610c59de6fa2e57009"  # Default key
    
    # Fetch player list from Data Golf API
    url = f"https://feeds.datagolf.com/get-player-list?file_format=json&key={api_key}"
    print(f"Fetching players from Data Golf API...")
    
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        players = response.json()
        print(f"Retrieved {len(players)} players from Data Golf API")
        
        # Ensure the database directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Insert players
        count = 0
        for player in players:
            try:
                cursor.execute('''
                INSERT OR IGNORE INTO players 
                (dg_id, name, amateur, country, country_code)
                VALUES (?, ?, ?, ?, ?)
                ''', (
                    player.get('dg_id'),
                    player.get('player_name'),
                    player.get('amateur', 0),
                    player.get('country'),
                    player.get('country_code')
                ))
                
                if cursor.rowcount > 0:
                    count += 1
                    
            except Exception as e:
                print(f"Error importing player {player.get('player_name')}: {e}")
        
        conn.commit()
        conn.close()
        
        print(f"Successfully imported {count} new players")
        return count
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching players from Data Golf API: {e}")
        return 0

if __name__ == "__main__":
    import_players_from_datagolf()