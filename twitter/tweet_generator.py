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
            raise ValueError("Anthropic API key not found in environment variables")
        
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
        WHERE id = ?
        """, (player_id,))

        player = cursor.fetchone()
        if not player:
            conn.close()
            raise ValueError(f"Player with ID {player_id} not found")
        
        player_data = dict(player)

        # Format player name for display (convert "last name, first name" to "first name last name")
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

        conn.close()
        return player_data
    
    def get_betting_data(self, player_id: int, markets: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get betting data for specified markets for a player.

        Args:
            player_id: Database ID of the player
            markets: List of betting markets to include (e.g., ["win", "top_5"])

        Returns:
            Dictionary of betting markets data organized by market
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
            "betonline": "BetOnline",
            "draftkings": "DraftKings",
            "fanduel": "FanDuel",
            "bet365": "Bet365",
            "bovada": "Bovada",
        }
        return book_display.get(book_code, book_code.capitalize())
    
    def generate_tweet(self, player_id: int, markets: List[str], tournament_name: Optional[str] = None, recent_tweets: List[str] = None) -> Tuple[str, Dict[str, Any]]:
        """
        Generate a tweet about a player's mental state and betting recommendations.

        Args:
            player_id: Database ID of the player
            markets: List of betting markets to analyze
            tournament_name: Name of the tournament (overrides the one from betting data if provided)
            recent_tweets: List of recent tweets to avoid repetition

        Returns:
            Tuple of(tweet text, context data used to generate the tweet)
        """

        # Get player data
        player_data = self.get_player_data(player_id)

        # Get betting data for specified markets
        betting_data = self.get_betting_data(player_id, markets)

        # Extract the player's full name and any nickname
        player_full_name = player_data["display_name"]
        player_nickname = player_data.get("nicknames", "None")

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
            "recent_tweets": recent_tweets or [],
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # Create the initial tweet generation prompt
        prompt = self._create_prompt(context)
        
        print(f"\n==== FULL PROMPT ====\n{prompt}\n==== END PROMPT ====\n")
        
        # Initialize the Anthropic client
        client = anthropic.Anthropic(api_key=self.api_key)

        # Set up for retries if needed
        max_attempts = 3
        attempt = 0
        final_tweet = None

        while attempt < max_attempts:
            attempt += 1
            print(f"Attempt {attempt}/{max_attempts} to generate a valid tweet")
            
            if attempt == 1:
                # First attempt - create the initial tweet
                initial_message = client.messages.create(
                    model="claude-3-7-sonnet-20250219",
                    max_tokens=1000,
                    temperature=0.7,
                    system=self.persona,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                
                # Extract the initial tweet
                tweet_text = initial_message.content[0].text.strip()
                print(f"Initial tweet ({len(tweet_text)} chars):\n{tweet_text}\n")
                
                # Validation step - continue the conversation
                validation_prompt = f"""Thanks for writing that tweet. Now let's validate it against our requirements:

        1) Did you use either the full name "{player_full_name}" or an appropriate nickname when first introducing the player so your followers understand who you're talking about? If no, please revise the tweet. If yes, please proceed to step 2.

        2) Is the tweet completely self-contained? Would it make complete sense to your followers, who won't have access to the player's assessment? If no, please revise the tweet. If yes, please proceed to step 3.

        3) Is the tweet 280 characters or less? If no, please revise the tweet to meet the character limit without truncating it and without violating step 1 and step 2. If yes, please post the tweet again with no additional explanation.

        Note: If you need to revise the tweet at any step, make sure your revised version meets ALL previous requirements."""
                
                validation_message = client.messages.create(
                    model="claude-3-7-sonnet-20250219",
                    max_tokens=1000,
                    temperature=0.7,
                    messages=[
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": tweet_text},
                        {"role": "user", "content": validation_prompt}
                    ]
                )
                
                # Extract the validated tweet
                final_tweet = validation_message.content[0].text.strip()
                
            else:
                # Check if the tweet is actually too long before telling the LLM it's too long
                if len(final_tweet) <= 280:
                    # If it's not too long, we're done
                    print(f"Validated tweet is under 280 characters, no need for additional attempts")
                    break
                    
                # Retry attempts - be more direct about character limit
                retry_prompt = f"""Your previous tweet is STILL too long ({len(final_tweet)} characters). 
                
        Twitter has a STRICT 280 CHARACTER LIMIT. Please rewrite your tweet to be UNDER 280 CHARACTERS while:
        1) Still using the full name "{player_full_name}"or a nickname when first introducing the player
        2) Keeping the tweet self-contained and meaningful to followers
        3) Maintaining the same analysis and recommendation

        Make it shorter by being more concise. Remove unnecessary words, but keep the essential information and analysis. 
        
        Just provide the rewritten tweet with no explanation."""
                
                retry_message = client.messages.create(
                    model="claude-3-7-sonnet-20250219",
                    max_tokens=1000,
                    temperature=0.7,
                    messages=[
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": tweet_text},
                        {"role": "user", "content": validation_prompt},
                        {"role": "assistant", "content": final_tweet},
                        {"role": "user", "content": retry_prompt}
                    ]
                )
                
                final_tweet = retry_message.content[0].text.strip()
            
            # Check if the tweet is within the character limit
            print(f"Validated tweet ({len(final_tweet)} chars):\n{final_tweet}\n")
            
            if len(final_tweet) <= 280:
                print(f"Successfully generated a valid tweet on attempt {attempt}")
                break
                
            if attempt == max_attempts:
                # If all attempts fail, we return the final tweet even if it's too long
                print(f"Warning: All {max_attempts} attempts failed to create a tweet under 280 characters.")
                print(f"Returning tweet with {len(final_tweet)} characters (over the limit).")
        
        # Return the final tweet AND context as a tuple
        return final_tweet, context
 
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
        recent_tweets = context.get("recent_tweets", [])

        player_name = player["display_name"]
        mental_score = player["mental_form"]["score"]
        justification = player["mental_form"]["justification"]

        prompt = f"""
Please compose a tweet as the Head Pro analyzing {player_name}'s current mental state and how it affects his betting value for an upcoming tournament: {tournament}.

According to your notes, {player_name} has a current mental form score of {mental_score if mental_score is not None else 'unknown'} (on a scale from -1 to 1). This score is based on your following assessment:

    "{justification}"

According to your betting model, which combines traditional strokes gained stats with your proprietary mental score, the fair odds for {player_name} are as follows:

=== HEAD PRO MODEL ==="""

        # Add model probabilities for each market
        for market_code, market_data in betting["markets"].items():
            market_name = market_code.upper()

            # If we have model probability data, calculate odds
            model_prob = None
            for bet in market_data:
                if bet.get("model_probability") is not None:
                    model_prob = bet.get("model_probability")
                    break
            
            if model_prob and model_prob > 0:
                # Convert probability to American odds
                if model_prob < 50:  # Underdog
                    model_odds = f"+{int(round((100 / model_prob) - 1) * 100)}"
                else:  # Favorite
                    model_odds = f"-{int(round(100 / (1 - (model_prob / 100))))}"
            else:
                model_odds = "N/A"

            prompt += f"\n{market_name}: {model_odds}"

        prompt += f"""

=== MARKET ODDS ===
The best available sportsbook odds and their expected values ("EV") are as follows:"""

        # Add best available odds for each market
        for market_code, market_data in betting["markets"].items():
            market_name = market_code.upper()

            if not market_data:
                prompt += f"\n{market_name}: No odds available"
                continue

            # Find the bet with the best EV
            best_bet = max(market_data, key=lambda x: x.get("adjusted_ev", 0)) if market_data else None

            if best_bet:
                american_odds = best_bet.get("american_odds", "N/A")
                adjusted_ev = best_bet.get("adjusted_ev", 0)
                prompt += f"\n{market_name}: {american_odds} (EV: {adjusted_ev:.1f}%)"
            else:
                prompt += f"\n{market_name}: No odds available"

        prompt += f"""

=== ANALYSIS INSTRUCTIONS ===
Your task is to compose a tweet (maximum 280 characters) analyzing one or two of these bets. Here are your betting guidelines:

    1. BACK a bet when:
        - The EV is over +7% for placement bets (or over +20% for outright winner bets) AND
        - The player's mental score is over +0.25. Never recommend backing a player with a negative mental score, even if the model shows +EV. The mental flags override the model.

    2. FADE a bet when:
        - The EV is less than 7%
        - The player's mental score is negative

    3. WAIT AND SEE when:
        - The player has a positive mental score over +0.25 but the EV is barely negative or not positive enough
        - The player's mental score is slightly positive (less than +0.25) - you need more positive mental indicators

=== NICKNAMES AND NOTES ===
To give you a little more flavor, here are some nicknames and background notes for the player. They don't factor into the model - they're just for fun. Use them sparingly, if at all:
        
NICKNAMES: {player.get('nicknames', 'None')}
    
NOTES: {player.get('notes', 'None')}

"""

        # Add the recent tweets section to avoid repetition if we have any
        if recent_tweets:
            # Get the most recent tweets (up to 10)
            max_tweets = min(10, len(recent_tweets))
            recent_tweet_examples = recent_tweets[:max_tweets]

            prompt += f"""
=== RECENT TWEETS ===
For variety, please avoid being too similar to your recent tweets. Create something fresh and different in structure and phrasing while maintaining your trademark HEAD PRO voice:        
"""

            for i, tweet in enumerate(recent_tweet_examples):
                prompt += f"\n{i+1}. {tweet}"

        prompt += f"""
=== OUTPUT INSTRUCTIONS ===
Your tweet MUST be UNDER 280 CHARACTERS and completely SELF-CONTAINED.

A self-contained tweet means:
1. Write like your followers don't have access to the assessment, because they don't! Assume your followers know nothing about the player.
2. Always use either the player's full name or a nickname so your followers know who you're talking about. Say either "Charlie Hoffman" or "Chuck Hoffman" instead of just "Hoffman."
3. Never mention raw numbers without context
4. Never explicitly reference the prompt (don't say shit like "That +3000" or "WAIT AND SEE"). In fact, don't use quotation marks at all.

Now go do your thing, Head Pro. Just write the tweet text itself with no additional explanation.
"""
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
    


                       
                       