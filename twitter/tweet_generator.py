"""
Tweet content generator for golf betting insights.

This module handles generating tweets in the Fat Phil persona
based on insights from the tournament data.
"""

import os
import random
import logging
from typing import List, Optional
import anthropic

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('twitter.generator')

class TweetGenerator:
    """Generates tweets in the Fat Phil persona based on golf insights"""
    
    def __init__(self, anthropic_api_key: Optional[str] = None, debug: bool = False):
        """
        Initialize the tweet generator.
        
        Args:
            anthropic_api_key: Optional API key for Anthropic (defaults to env var)
            debug: If True, enable additional debugging output
        """
        # Use provided API key or get from environment
        self.api_key = anthropic_api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("Anthropic API key is required. Set ANTHROPIC_API_KEY environment variable or pass to constructor.")
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.persona = self._load_persona()
        self.debug = debug
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
    
    def generate_tweet(self, insights_file: str, recent_tweets: List[str] = None) -> str:
        """
        Generate a tweet in the Fat Phil persona based on insights.
        
        Args:
            insights_file: Path to the insights text file
            recent_tweets: List of recent tweets to avoid repetition
            
        Returns:
            Generated tweet text
            
        Raises:
            Exception: If tweet generation fails for any reason
        """
        try:
            # Load the entire insights file
            with open(insights_file, 'r', encoding='utf-8') as f:
                insights_content = f.read()
            
            # Get a list of player names from the insights file for random selection
            player_names = []
            lines = insights_content.split('\n')
            for line in lines:
                if line.startswith('**') and line.endswith('**'):
                    player_name = line.strip('*')
                    player_names.append(player_name)
            
            # Randomly select a player to focus on
            selected_player = random.choice(player_names) if player_names else None
            
            # Create the tweet generation prompt
            tweet_prompt = f"""
    Based on the golf betting insights below, create a single tweet as Fat Phil about {selected_player if selected_player else 'a player of your choice'} for the upcoming tournament. Focus on a specific betting angle that provides value.

    BETTING INSIGHTS:
    {insights_content}

    Create ONE concise tweet (max 280 characters) in Fat Phil's voice. Make it direct, colorful, and valuable to bettors. Focus on a specific betting angle, not just general information. Just write the tweet text itself with no additional explanation.
    """

            # Add recent tweets to avoid repetition
            if recent_tweets and len(recent_tweets) > 0:
                tweet_prompt += "\n\nDO NOT repeat ideas from these recent tweets:\n"
                for tweet in recent_tweets[:5]:  # Only use last 5 tweets
                    tweet_prompt += f"- {tweet}\n"
            
            # Generate tweet using Claude
            logger.info(f"Generating tweet about {selected_player if selected_player else 'a random player'}")

                    # Log the complete prompt (both system and user messages)
            logger.info(f"Selected player: {selected_player if selected_player else 'random player'}")
            logger.info("---- COMPLETE PROMPT START ----")
            logger.info(f"SYSTEM PROMPT:\n{self.persona}")
            logger.info(f"USER PROMPT:\n{tweet_prompt}")
            logger.info("---- COMPLETE PROMPT END ----")
            
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
            raise  # Re-raise the exception instead of returning a fallback tweet


# Example usage (commented out)
"""
if __name__ == "__main__":
    generator = TweetGenerator()
    
    # Generate a tweet based on insights file
    tweet = generator.generate_tweet("valspar_championship_2025-03-19_insights_only.txt")
    print(f"Generated tweet: {tweet}")
"""