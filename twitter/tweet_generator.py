"""
This module handles the generation of tweets for The Head Pro,
using the Anthropic Claude API to create insightful, character-driven
content about golfers' mental states and betting recommendations.
"""

import os
import json
import datetime
import sqlite3
import anthropic
from typing import Dict, List, Optional, Any, Tuple
from dotenv import load_dotenv

load_dotenv()

class HeadProTweetGenerator:
    def __init__(self, persona_file: str = "head_pro_persona.txt", db_path: str = "data/db/mental_form.db"):
        """
        Initialize the Head Pro tweet generator.

        Args:
            persona_file: Path to the file containing the Head Pro's persona description
            db_path: Path to the database containing player and betting data
        """
        self.db_path = db_path
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("Anthropic API key not found in environmentmal variables")
        
        # Load the Head Pro persona
        try:
            with open(persona_file, 'r', encoding='utf-8') as f:
                self.persona = f.read()
        except Exception as e:
            error_msg = f"Critical error: Could not load persona file: {e}"
            print(error_msg)
            raise RuntimeError(error_msg)
        
    def _get_db_connection(self) -> sqlite3.Connection:
        """Get a connection to the database"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_player_data(self, player_id: int) -> Dict[str, Any]:
        """
        Get all relevant player data for a player needed to generate a tweet.

        Args:
            player_id: Database ID of the player

        Returns:
            Dictionary containing player information, mental form, insights, and betting data
        """
        conn = self._get_db_connection()
        cursor = conn.cursor()

        # Get player basic info
        cursor.execute("""
        SELECT id, name, nicknames, notes
        FROM players
        Where id = ?
        """, (player_id,))

        player = cursor.fetchone()
        if not player:
            conn.close()
            raise ValueError(f"Player with ID {player_id} not found")
        
        player_data = dict(player)

        # Format player name for display (convert "last name, first name" to "fist name last name")
        if ',' in player_data['name']:
            last, first = player_data['name'].split(',', 1)
            player_data['display_name'] = f"{first.strip()} {last.strip()}"
        else:
            player_data['display_name'] = player_data['name']

        # Get mental form score and justification
        cursor.execute("""
        SELECT score, justification, last_updated
        FROM mental_form
        WHERE player_id = ?
        """, (player_id,))

        mental_form = cursor.fetchone()
        if mental_form:
            player_data['mental_form'] = dict(mental_form)
        else:
            player_data['mental_form'] = {
                'score': None,
                'justification': "No mental form data available.",
                'last_updated': None
            }
        
        # Get recent insights (most recent 10)
        cursor.execute("""
        SELECT text, source, date
        FROM insights
        WHERE player_id = ?
        ORDER BY date DESC
        LIMIT 15
        """, (player_id,))

        player_data['insights'] = [dict(insight) for insight in cursor.fetchall()]

        conn.close()
        return player_data
    
    def get_betting_data(self, player_id: int, markets: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get betting data for specified markets for a player.

        Args:
            player_id: Database ID of the player
            markets: List of betting markets to include (e.g., ["win", "top_5"])

        Returns:
            Dictionary of betting markets data organzied by market
        """

        conn = self._get_db_connection()
        cursor = conn.cursor()

        # Get the current tournament
        cursor.execute("""
        SELECT event_name, MAX(timestamp) as latest
        FROM bet_recommendations
        GROUP BY event_name
        ORDER BY latest DESC
        LIMIT 1
        """)

        event_result = cursor.fetchone()
        if not event_result:
            conn.close()
            return {"event_name": None, "markets":{}}
        
        event_name = event_result['event_name']

        # Get betting data for each requested market
        betting_data = {
            "event_name": event_name,
            "markets": {}
        }

        for market in markets:
            cursor.execute("""
            SELECT sportsbook, decimal_odds, base_ev, mental_adjustment, adjusted_ev, model_probability
            FROM bet_recommendations
            WHERE player_id = ? AND event_name = ? AND market = ?
            ORDER BY adjusted_ev DESC
            """, (player_id, event_name, market))

            market_data = [dict(bet) for bet in cursor.fetchall()]

            # Format each bet with American odds
            for bet in market_data:
                decimal_odds = bet['decimal_odds']
                if decimal_odds >= 2.0:
                    american_odds = f"+{int(round((decimal_odds - 1) * 100))}"
                else:
                    american_odds = f"{int(round(-100 / (decimal_odds - 1)))}"

                bet['american_odds'] = american_odds

            betting_data["markets"][market] = market_data

        conn.close()
        return betting_data
    
    def format_market_name(self, market_code: str) -> str:
        """Format market code into a readable name"""
        market_display = {
            "win": "Outright Winner",
            "top_5": "Top 5 Finish",
            "top_10": "Top 10 Finish",
            "top_20": "Top 20 Finish",
            "make_cut": "Make Cut",
            "mc": "Miss Cut",
            "frl": "First Round Leader"
        }
        return market_display.get(market_code, market_code.upper())
    
    def format_sportsbook_name(self, book_code: str) -> str:
        """Format sportsbook code into a readable name"""
        book_display = {
            "betmgm": "BetMGM",
            "draftkings": "DraftKings",
            "fanduel": "FanDuel",
            "bet365": "Bet365",
            "bovada": "Bovada",
        }
        return book_display.get(book_code, book_code.capitalize())
    
    def generate_tweet(self, player_id: int, markets: List[str], tournament_name: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
        """
        Generate a tweet about a player's mental state and betting recommendations.

        Args:
            player_id: Database ID of the player
            markets: List of betting markets to analyze
            tournament_name: Name of the tournament (overrides the one from betting data if provided)

        Returns:
            Tuple of(tweet text, context data used to generate the tweet)
        """

        # Get player data
        player_data = self.get_player_data(player_id)

        # Get betting data for specified markets
        betting_data = self.get_betting_data(player_id, markets)

        # Override tournament name if provided
        if tournament_name:
            event_name = tournament_name
        elif "event_name" in betting_data and betting_data["event_name"]:
            event_name = betting_data["event_name"]
        else:
            raise ValueError("No tournament name provided and none found in betting data")
        
        # Create context for LLM
        context = {
            "player": player_data,
            "betting": betting_data,
            "tournament": event_name,
            "markets": [self.format_market_name(m) for m in markets],
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # Create the tweet generation prompt
        prompt = self._create_prompt(context)

        # Call LLM to generate the tweet
        client = anthropic.Anthropic(api_key=self.api_key)

        message = client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=1000,
            temperature=0.7,
            system=self.persona,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        tweet_text = message.content[0].text.strip()

        return tweet_text, context
    
    def _create_prompt(self, context: Dict[str, Any]) -> str:
        """
        Create a prompt for an LLM to generate a tweet.

        Args:
            context: Dictionary containing all the data needed for the tweet

        Returns:
            Prompt string to send to Claude
        """

        player = context["player"]
        betting = context["betting"]
        tournament = context["tournament"]
        markets = context["markets"]

        player_name = player["display_name"]
        mental_score = player["mental_form"]["score"]
        justification = player["mental_form"]["justification"]

        prompt = f"""
Please compose a tweet as the Head Pro analyzing {player_name}'s current mental state and how it affects his betting value for {tournament}.

Your analysis should be based on:
1. His current mental form score of {mental_score if mental_score is not None else 'unknown'} (on a scale from -1 to 1)
2: Your justification for this score: "{justification}"json
3: The betting data for these markets: {', '.join(markets)}

Make a clear recommendation on whether bettors should either back or fade this player in specific markets, based on his mental score and betting value. Specifically comment on the Adjusted EV values, which incorporate the mental adjustment.

The tweet must be under 280 characters. Be pithy but insightful. Short and punchy sentences. Less is more.

For additional context, here are some recent insights excerpted from various media sources about {player_name}:
"""
        # Add insights
        for i, insight in enumerate(player["insights"]):
            prompt += f"\n{i+1}. [{insight['date']}] {insight['text']}"

        # Add betting data
        prompt += f"\n\nBetting_data for {player_name} at {tournament}:"

        for market_code, market_data in betting["markets"].items():
            market_name = self.format_market_name(market_code)
            prompt += f"\n\n{market_name} Market:"

            if not market_data:
                prompt += " No odds available"
                continue

            for bet in market_data:
                sportsbook = self.format_sportsbook_name(bet["sportsbook"])
                adjusted_ev = bet["adjusted_ev"]
                american_odds = bet["american_odds"]
                
                prompt += f"\n- {sportsbook}: {american_odds} (Adjusted EV: {adjusted_ev:.1f}%)"

        # Add any nicknames or notes if available
        if player.get("nicknames"):
            prompt += f"\n\nPlayer nicknames: {player['nicknames']}"
            
        if player.get("notes"):
            prompt += f"\n\nAdditional player notes: {player['notes']}"

        prompt += "\n\nNow generate your tweet:"

        return prompt
    
if __name__ == "__main__":
    # Example usage
    generator = HeadProTweetGenerator()
    tweet, context = generator.generate_tweet(
        player_id=123, # Replace with actual player ID
        markets=["win", "top_5", "top_10"],
        tournament_name="The Masters"
    )
    print(f"Generated tweet ({len(tweet)} characters):")
    print(tweet)
    


                       
                       