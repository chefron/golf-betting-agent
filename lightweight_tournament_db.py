"""
This module creates a simplified tournament database that only contains
player names, IDs, and insights without pre-fetching all the odds data.
"""

import os
import json
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('golf.tournament_db')

load_dotenv()

class LightweightTournamentDB:
    """Builds and manages lightweight tournament databases"""
    
    def __init__(self):
        """
        Initialize the database builder.
        """
        # Get API key from environment
        self.api_key = os.getenv('DATAGOLF_API_KEY') or "6e301f31eb610c59de6fa2e57009"
        self.base_url = "https://feeds.datagolf.com"
        logger.info("Initialized LightweightTournamentDB")
    
    def fetch_api_data(self, endpoint, params=None):
        """
        Fetch data from the DataGolf API.
        
        Args:
            endpoint: API endpoint path
            params: Query parameters
            
        Returns:
            JSON response from the API
        """
        if params is None:
            params = {}
        
        # Add API key to params
        params['key'] = self.api_key
        
        # Build full URL
        url = f"{self.base_url}/{endpoint}"
        
        logger.info(f"Fetching: {url}")
        
        try:
            # Make the request
            response = requests.get(url, params=params)
            response.raise_for_status()  # Raise exception for HTTP errors
            
            # Return JSON data
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching data from DataGolf API: {e}")
            return None
    
    def build_database(self):
        """
        Build a lightweight tournament database.
        
        Returns:
            Dictionary with tournament information and players
        """
        try:
            # Get tournament information and player field from the same endpoint
            response = self.fetch_api_data("betting-tools/outrights", {
                "tour": "pga",
                "market": "win",
                "odds_format": "decimal"
            })
            
            if not response:
                raise ValueError("Failed to fetch tournament data")
                
            # Extract tournament info
            tournament_info = {
                "name": response.get("event_name", "Unknown Tournament"),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "last_updated": response.get("last_updated", datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")),
                "tour": "pga"
            }
            
            logger.info(f"Building database for {tournament_info['name']}")
            
            # Extract players
            players = []
            seen_ids = set()  # Track IDs to avoid duplicates
            
            for player in response.get("odds", []):
                if "dg_id" in player and "player_name" in player:
                    player_id = str(player["dg_id"])
                    
                    # Skip duplicates
                    if player_id in seen_ids:
                        continue
                    
                    players.append({
                        "id": player_id,
                        "name": player["player_name"],
                        "insights": ""  # Empty insights to start
                    })
                    
                    seen_ids.add(player_id)
            
            if not players:
                raise ValueError("No players found in tournament field")
                
            logger.info(f"Retrieved {len(players)} players with betting odds")
            
            # Structure the database
            database = {
                "tournament": tournament_info,
                "players": {}
            }
            
            # Add players to the database
            for player in players:
                database["players"][player["id"]] = {
                    "id": player["id"],
                    "name": player["name"],
                    "insights": ""
                }
            
            return database
            
        except Exception as e:
            logger.error(f"Error building tournament database: {e}")
            raise
    
    def save_database(self, database, output_dir="data"):
        """
        Save the database to a JSON file.
        
        Args:
            database: Tournament database dictionary
            output_dir: Directory to save the file
            
        Returns:
            Path to the saved file
        """
        try:
            # Create the output directory if it doesn't exist
            os.makedirs(output_dir, exist_ok=True)
            
            # Create a filename from the tournament name
            tournament_name = database["tournament"]["name"]
            current_date = database["tournament"]["date"]
            filename = f"{tournament_name.lower().replace(' ', '_').replace('-', '_').replace('\'', '').replace('\"', '')}_{current_date}.json"
            filepath = os.path.join(output_dir, filename)
            
            # Write the database to a file
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(database, f, indent=2)
            
            logger.info(f"Saved tournament database to {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error saving tournament database: {e}")
            raise

if __name__ == "__main__":
    # Simplified to just build a new database
    print("Building new lightweight tournament database...")
    db_builder = LightweightTournamentDB()
    database = db_builder.build_database()
    filepath = db_builder.save_database(database)
    print(f"Database saved to {filepath}")