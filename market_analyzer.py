"""
This module analyzes player insights to determine the most relevant betting market endpoints.
"""

import os
import logging
import anthropic
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('golf.market_analyzer')

load_dotenv()

class MarketAnalyzer:
    """Analyzes player insights to determine relevant betting markets"""
    
    def __init__(self):
        """
        Initialize the market analyzer.
        """
        # Get API key from environment
        self.api_key = os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError("Anthropic API key is required. Set ANTHROPIC_API_KEY environment variable.")
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        logger.info("Initialized MarketAnalyzer")
    
    def analyze_insight(self, player_name, insight_text):
        """
        Analyze a player's insight to determine the most relevant betting markets.
        
        Args:
            player_name: The player's name
            insight_text: The player's insight text
            
        Returns:
            List of relevant market types to query
        """
        logger.info(f"Analyzing insights for {player_name}")
        
        # Valid market types
        valid_markets = ["win", "top_5", "top_10", "top_20", "make_cut", "mc", "frl"]
        
        # Create prompt for Claude with structured output format
        prompt = f"""
        Based on the following golf betting insight for {player_name}, please identify the most relevant betting markets 
        to focus on for this player.

        PLAYER INSIGHT:
        {insight_text}
        
        First, briefly explain your reasoning.

        Then, choose from these market types only:
        - win (outright winner)
        - top_5 (top 5 finish)
        - top_10 (top 10 finish)
        - top_20 (top 20 finish)
        - make_cut (to make the cut)
        - mc (to miss the cut)
        - frl (first round leader)

        Provide your answer in this specific format:

        REASONING: [Your reasoning here]

        MARKETS: [
          "market1",
          "market2"
        ]

        Choose only 1-3 markets that are MOST relevant based on the insights. The format of your MARKETS section 
        must be a valid JSON array with quoted strings.
        """
        
        try:
            # Query Claude
            response = self.client.messages.create(
                model="claude-3-7-sonnet-20250219",
                max_tokens=1000,
                temperature=0,
                system="You are a golf betting expert identifying the most relevant betting markets based on player insights.",
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = response.content[0].text.strip()
            
            # Always log Claude's full response for testing
            logger.info(f"Claude's full response for {player_name}:\n{response_text}")
            
            # Extract the markets from the response
            markets = []
            
            if "MARKETS:" in response_text:
                markets_section = response_text.split("MARKETS:")[1].strip()
                
                # Look for an array format with square brackets
                if "[" in markets_section and "]" in markets_section:
                    array_text = markets_section[markets_section.find("["):markets_section.find("]")+1]
                    
                    # Parse the markets, handling both comma-separated strings and JSON format
                    try:
                        import json
                        markets = json.loads(array_text)
                    except json.JSONDecodeError:
                        # Fallback to simple parsing if JSON parsing fails
                        array_content = array_text.strip("[]")
                        markets = [m.strip().strip('"\'') for m in array_content.split(",")]
                        markets = [m for m in markets if m]  # Remove empty strings
            
            # Validate the markets against our list of valid markets
            markets = [m for m in markets if m in valid_markets]
            
            # If no valid markets found, default to win and top_20
            if not markets:
                logger.warning(f"No valid markets identified for {player_name}, using defaults")
                markets = ["win", "top_20"]
            
            # Log the final selected markets
            logger.info(f"Selected markets for {player_name}: {markets}")
            return markets
            
        except Exception as e:
            logger.error(f"Error analyzing markets for {player_name}: {e}")
            # Fallback to safe defaults
            return ["win", "top_20"]