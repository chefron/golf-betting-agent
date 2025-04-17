"""
Main module for the Head Pro Twitter automation.

This script handles the scheduling and coordination of tweet generation
and posting for the Head Pro, analyzing golfers' mental states and
providing betting recommendations.

"""

import os
import json
import logging
import argparse
import datetime
from typing import List, Dict, Any, Optional
import time
import random
from pathlib import Path

from tweet_generator import HeadProTweetGenerator
from post import TwitterPoster

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("head_pro_tweets.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("head_pro.main")

class HeadProTwitterBot:
    def __init__(self,
                 config_file: str = "config.json",
                 db_path: str = "data/db/mental_form.db",
                 history_file: str = "twitter/tweet_history.json",
                 persona_file: str = "twitter/head_pro_persona.txt",
                 player_list_file: str = "twitter/player_list.json"):
        """
        Initialize the Head Pro Twitter bot.
        
        Args:

            config_file: Path to configuration file
            db_path: Path to SQLite database
            history_file: Path to tweet history file
            persona_file: Path to Head Pro persona description
            player_list_file: Path to file containing players to tweet about

        """
        self.config_file = config_file
        self.db_path = db_path
        self.history_file = history_file
        self.persona_file = persona_file
        self.player_list_file = player_list_file

        # Create directories if they don't exist
        os.makedirs(os.path.dirname(history_file), exist_ok=True)

        # Load configuration
        self.config = self._load_config()

        # Initialize components
        self.generator = HeadProTweetGenerator(
            persona_file=persona_file,
            db_path=db_path
        )

        self.poster = TwitterPoster(
            history_file=history_file
        )

        # Load player list
        self.player_list = self._load_player_list()

        logger.info("Head Pro Twitter bot initialized")

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from the config file."""
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            logger.info(f"Loaded configuration from {self.config_file}")
            return config
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load config from {self.config_file}: {e}")
            logger.info("Using default configuration")

            # Default configuration
            return {
                "default_markets": ["win", "top_5", "top_10", "top_20"],
                "review_mode": True,
                "tweet_interval_hours": 4,
                "random_interval_variation": 1.2, # +/- hours of randomness
                "active_hours": {
                    "start": 8, # 8am
                    "end": 22 # 10pm
                },
                "max_tweets_per_day": 9
            }
        
    def _load_player_list(self) -> List[Dict[str, Any]]:
        """Load the list of players to tweet about"""
        try:
            with open(self.player_list_file, 'r') as f:
                player_list = json.load(f)
            logger.info(f"Loaded player list from {self.player_list_file} with {len(player_list)} players")
            return player_list
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load player list from {self.player_list_file}: {e}")
            logger.info("Using empty player list. Please create a player list file.")
            return []
        
    def save_player_list(self) -> None:
        """Save the player list to file."""
        try:
            with open(self.player_list_file, 'w') as f:
                json.dump(self.player_list, f, indent=2)
            logger.info(f"Saved player list to {self.player_list_file}")
        except Exception as e:
            logger.error(f"failed to save player list: {e}")

    def update_player_list(self, new_player_list: List[Dict[str, Any]]) -> None:
        """Update the player list with new data."""
        self.player_list = new_player_list
        self.save_player_list()

    def get_next_player(self) -> Optional[Dict[str, Any]]:
        """
        Get the next player to tweet about.
        
        Players with 'priority' flag will be chosen first.
        Otherwise, players who haven't been tweeted about recently will be prioritized.
        
        Returns:
            Dictionary with player information or None if no player is available
        """
        if not self.player_list:
            logger.warning("Player list is empty")
            return None
        
        # First, look for priority players who haven't been tweeted
        priority_players = [p for p in self.player_list if p.get('priority') and not p.get('tweeted')]
        
        if priority_players:
            logger.info(f"Found {len(priority_players)} priority players to tweet about")
            return random.choice(priority_players)
        
        # Next, look for any players who haven't been tweeted yet
        untweeted_players = [p for p in self.player_list if not p.get('tweeted')]
        
        if untweeted_players:
            logger.info(f"Found {len(untweeted_players)} untweeted players")
            return random.choice(untweeted_players)
        
        # If all players have been tweeted about, don't reset - just notify and return None
        logger.info("All players have been tweeted about. No more players available to tweet about.")
        return None
    
    def mark_player_as_tweeted(self, player_id: int) -> None:
        """
        Mark a player as having been tweeted about.

        Args:
            player_id: The database ID of the player
        """
        for player in self.player_list:
            if player.get('id') == player_id:
                player['tweeted'] = True
                player['last_tweeted'] = datetime.datetime.now().isoformat()
                break
        
        self.save_player_list()






       
                    
                    
                    