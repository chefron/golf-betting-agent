"""
Tweet content generator for golf betting insights.

This module handles generating tweets in the Fat Phil persona
based on insights from the tournament data.
"""

import os
import json
import random
import logging
from typing import List, Optional, Dict
import anthropic
from dotenv import load_dotenv

from market_analyzer import MarketAnalyzer
from odds_retriever import OddsRetriever

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('twitter.generator')

# Load environment variables
load_dotenv()

class TweetGenerator:
    """Generates tweets in the Fat Phil persona based on golf insights"""
    
    def __init__(self, anthropic_api_key: Optional[str] = None, datagolf_api_key: Optional[str] = None, debug: bool = False):
        """
        Initialize the tweet generator.
        
        Args:
            anthropic_api_key: Optional API key for Anthropic (defaults to env var)
            datagolf_api_key: Optional API key for DataGolf (defaults to env var)
            debug: If True, enable additional debugging output
        """
        # Use provided API key or get from environment
        self.api_key = anthropic_api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("Anthropic API key is required. Set ANTHROPIC_API_KEY environment variable or pass to constructor.")
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.persona = self._load_persona()
        self.debug = debug
        
        # Initialize helper components
        self.market_analyzer = MarketAnalyzer(anthropic_api_key=self.api_key, debug=debug)
        self.odds_retriever = OddsRetriever(api_key=datagolf_api_key, debug=debug)
        
        logger.info("Initialized TweetGenerator")
    
    def _load_persona(self) -> str:
        """
        Load the Fat Phil persona from the persona.txt file.
        
        Returns:
            The persona text content
        """
        try:
            persona_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'persona.txt')
            with open(persona_path, 'r', encoding='utf-8') as f:
                persona = f.read().strip()
            logger.info("Loaded Fat Phil persona")
            return persona
        except Exception as e:
            logger.error(f"Error loading persona: {e}")
            # Fallback minimal persona in case file is missing
            return "You are Fat Phil, a flamboyant, straight-talking golf betting expert from Las Vegas."
    
    def select_player(self, json_file: str) -> Dict:
        """
        Select a player from the tournament database.
        
        Args:
            json_file: Path to the tournament JSON file
            
        Returns:
            Dictionary with player data
        """
        try:
            # Load the tournament database
            with open(json_file, 'r', encoding='utf-8') as f:
                tournament_data = json.load(f)
            
            # Find players with insights
            players_with_insights = []
            for player_id, player_data in tournament_data["players"].items():
                if player_data.get("insights") and player_data.get("insights").strip() != "":
                    players_with_insights.append((player_id, player_data))
            
            if not players_with_insights:
                raise ValueError("No players with insights found in the tournament database")
            
            # Randomly select a player
            player_id, player_data = random.choice(players_with_insights)
            
            # Extract relevant information
            player_info = {
                "id": player_id,
                "name": player_data["name"],
                "insights": player_data["insights"],
                "tournament_name": tournament_data["tournament"]["name"],
                "tournament_date": tournament_data["tournament"]["date"]
            }
            
            logger.info(f"Selected player: {player_info['name']}")
            return player_info
            
        except Exception as e:
            logger.error(f"Error selecting player: {e}")
            raise
    
    def enrich_player_data(self, player_info: Dict) -> Dict:
        """
        Enrich player data with relevant betting markets and odds.
        
        Args:
            player_info: Basic player information
            
        Returns:
            Dictionary with player data enriched with odds
        """
        try:
            # First, analyze the player's insight to identify relevant markets
            markets = self.market_analyzer.analyze_insight(player_info["name"], player_info["insights"])
            
            # Next, fetch odds for those markets
            odds = self.odds_retriever.fetch_relevant_odds(
                player_info["id"], 
                player_info["name"], 
                markets
            )
            
            # Add odds to player info
            player_info["odds"] = odds
            
            markets_found = list(odds.keys())
            logger.info(f"Enriched {player_info['name']}'s data with odds for these markets: {', '.join(markets_found)}")
            
            return player_info
            
        except Exception as e:
            logger.error(f"Error enriching player data: {e}")
            # Still return the basic player info even if we couldn't get odds
            return player_info
    
    def format_odds_for_prompt(self, odds_data: Dict) -> str:
        """
        Format odds data for inclusion in the tweet prompt.
        
        Args:
            odds_data: Dictionary of market odds
            
        Returns:
            Formatted odds text
        """
        if not odds_data:
            return "No odds data available."
        
        odds_text = ""
        
        for market, market_data in odds_data.items():
            # Add market header
            odds_text += f"{market_data['display_name']}:\n"
            
            # Add model odds
            model_prob = market_data["model_probability"]
            model_decimal = market_data["model_decimal"]
            odds_text += f"- Model: {model_decimal:.2f} ({model_prob:.1f}%)\n"
            
            # Add top sportsbooks with best EV (limited to top 3)
            if market_data["sportsbooks"]:
                books_text = []
                for book in market_data["sportsbooks"][:3]:  # Top 3 by EV
                    ev_sign = "+" if book["ev"] >= 0 else ""
                    books_text.append(f"{book['display_name']}: {book['odds']:.2f} ({ev_sign}{book['ev']:.1f}%)")
                
                odds_text += f"- Best odds: {' | '.join(books_text)}\n"
            
            odds_text += "\n"
        
        return odds_text
    
    def generate_tweet(self, json_file: str, recent_tweets: List[str] = None) -> str:
        """
        Generate a tweet in the Fat Phil persona based on insights.
        
        Args:
            json_file: Path to the tournament JSON file
            recent_tweets: List of recent tweets to avoid repetition
            
        Returns:
            Generated tweet text
            
        Raises:
            Exception: If tweet generation fails for any reason
        """
        try:
            # Select a player
            player_info = self.select_player(json_file)
            
            # Enrich with relevant betting markets and odds
            enriched_player = self.enrich_player_data(player_info)
            
            # Format odds for the prompt
            odds_text = self.format_odds_for_prompt(enriched_player.get("odds", {}))
            
            # Create the tweet generation prompt
            tweet_prompt = f"""
Based on the following golf betting insights and odds, create a single tweet as Fat Phil about {enriched_player['name']} for the {enriched_player['tournament_name']}. Focus on the most valuable betting angle that provides the best edge.

PLAYER: {enriched_player['name']}

TOURNAMENT: {enriched_player['tournament_name']} ({enriched_player['tournament_date']})

BETTING INSIGHTS:
{enriched_player['insights']}

RELEVANT ODDS:
{odds_text}

Create ONE concise tweet (max 280 characters) in Fat Phil's voice. Make it direct, colorful, and valuable to bettors. Focus on the specific betting angle with the best value, not just general information. Just write the tweet text itself with no additional explanation.
"""

            # Add recent tweets to avoid repetition
            if recent_tweets and len(recent_tweets) > 0:
                tweet_prompt += "\n\nDO NOT repeat ideas from these recent tweets:\n"
                for tweet in recent_tweets[:5]:  # Only use last 5 tweets
                    tweet_prompt += f"- {tweet}\n"
            
            # Generate tweet using Claude
            logger.info(f"Generating tweet about {enriched_player['name']}")

            if self.debug:
                # Log the complete prompt (both system and user messages)
                logger.debug("---- COMPLETE PROMPT START ----")
                logger.debug(f"SYSTEM PROMPT:\n{self.persona}")
                logger.debug(f"USER PROMPT:\n{tweet_prompt}")
                logger.debug("---- COMPLETE PROMPT END ----")
            
            response = self.client.messages.create(
                model="claude-3-7-sonnet-20250219",
                max_tokens=1000,
                temperature=0.7,  # Slightly higher temperature for creativity
                system=self.persona,
                messages=[
                    {"role": "user", "content": tweet_prompt}
                ]
            )
            
            tweet_text = response.content[0].text.strip()
            
            # Remove any quotation marks that might have been added
            tweet_text = tweet_text.strip('"\'')
            
            logger.info(f"Generated tweet: {tweet_text}")
            return tweet_text
            
        except Exception as e:
            logger.error(f"Error generating tweet: {e}")
            raise  # Re-raise the exception