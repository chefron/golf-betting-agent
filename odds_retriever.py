"""
This module retrieves odds from the DataGolf API for specific players and markets.
It also integrates mental form scores to calculate adjusted EV for betting recommendations.
"""

import logging
import requests
import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('golf.odds_retriever')

load_dotenv()

class OddsRetriever:
    """Retrieves odds from DataGolf API and calculates adjusted EV using mental form scores"""
    
    def __init__(self, db_path="data/db/mental_form.db"):
        """
        Initialize the odds retriever.
        
        Args:
            db_path: Path to SQLite database with mental form scores
        """
        # Get API key from environment
        self.api_key = os.getenv('DATAGOLF_API_KEY') or "6e301f31eb610c59de6fa2e57009"
        self.base_url = "https://feeds.datagolf.com"
        self.db_path = db_path
        logger.info("Initialized OddsRetriever")
    
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
    
    def calculate_ev(self, model_probability, decimal_odds):
        """
        Calculate Expected Value (EV) percentage.
        
        Args:
            model_probability: Model probability as percentage
            decimal_odds: Decimal odds from sportsbook
            
        Returns:
            EV percentage
        """
        # Handle zero or invalid inputs
        if not model_probability or not decimal_odds or decimal_odds <= 1:
            return 0
        
        # Convert percentage to decimal
        prob = model_probability / 100
        
        # Calculate EV
        ev = (prob * (decimal_odds - 1)) - (1 - prob)
        
        # Convert to percentage
        ev_pct = ev * 100
        
        return ev_pct
    
    def get_player_mental_score(self, dg_id):
        """
        Get the mental form score for a player from the database.
        
        Args:
            dg_id: DataGolf player ID
            
        Returns:
            Mental form score (-1 to 1) or None if not found
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT m.score
            FROM mental_form m
            JOIN players p ON m.player_id = p.id
            WHERE p.dg_id = ?
            ''', (dg_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return result['score']
            return None
            
        except Exception as e:
            logger.error(f"Error fetching mental score: {e}")
            return None
    
    def calculate_adjusted_ev(self, model_probability, decimal_odds, mental_score, market=None):
        """
        Calculate Expected Value (EV) adjusted by mental score.
        
        Args:
            model_probability: Model probability as percentage
            decimal_odds: Decimal odds from sportsbook
            mental_score: Mental form score (-1 to 1)
            market: Market type (e.g., "win", "top_5", "mc")
            
        Returns:
            Tuple of (adjusted EV percentage, adjustment percentage)
        """
        # Calculate base EV
        base_ev = self.calculate_ev(model_probability, decimal_odds)
        
        # If no mental score, return base EV
        if mental_score is None:
            return base_ev, 0
        
        # Determine adjustment direction based on market type
        # For "miss cut" (MC) market, reverse the adjustment direction
        # because poor mental form (negative score) increases chance of missing cut
        adjustment_direction = -1 if market == "mc" else 1
        
        # Adjust model probability based on mental score and market type
        # For standard markets (like win, top_5):
        #   - Positive mental scores increase the probability (max +15%)
        #   - Negative mental scores decrease the probability (max -15%)
        # For "miss cut" market, the adjustment is reversed
        adjustment_factor = mental_score * 0.15 * adjustment_direction
        adjusted_probability = model_probability * (1 + adjustment_factor)
        
        # Ensure probability doesn't exceed 100% or go below 0%
        adjusted_probability = min(max(adjusted_probability, 0), 100)
        
        # Recalculate EV with adjusted probability
        adjusted_ev = self.calculate_ev(adjusted_probability, decimal_odds)
        
        return adjusted_ev, adjustment_factor * 100
    
    def update_odds_data(self, markets=None):
        """
        Update odds for all players in the current tournament and
        calculate adjusted EV based on mental scores.
        
        Args:
            markets: List of markets to update (defaults to all)
            
        Returns:
            Dictionary with event information and processed odds data
        """
        if markets is None:
            markets = ["win", "top_5", "top_10", "top_20", "make_cut", "mc", "frl"]
        
        result = {
            "event_name": None,
            "last_updated": None,
            "markets": {market: [] for market in markets}
        }
        
        # Get odds data for first market to extract event info
        first_market_data = self.fetch_api_data("betting-tools/outrights", {
            "tour": "pga",
            "market": markets[0],
            "odds_format": "decimal"
        })
        
        if not first_market_data or "event_name" not in first_market_data:
            logger.error("Could not fetch event info from betting data")
            return result
        
        # Use a single timestamp for the entire batch
        self.current_batch_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        event_name = first_market_data["event_name"]
        result["event_name"] = event_name
        result["last_updated"] = self.current_batch_timestamp
        
        # Fetch all players from database with their mental scores
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT p.id, p.name, p.dg_id, m.score
        FROM players p
        LEFT JOIN mental_form m ON p.id = m.player_id
        ''')
        
        # Create a lookup dictionary for players
        players_by_dg_id = {}
        players_by_name = {}
        
        for player in cursor.fetchall():
            if player['dg_id']:
                players_by_dg_id[str(player['dg_id'])] = {
                    'id': player['id'],
                    'name': player['name'],
                    'mental_score': player['score']
                }
            
            name_parts = player['name'].split(', ')
            if len(name_parts) > 1:
                last_name = name_parts[0].lower()
                players_by_name[last_name] = {
                    'id': player['id'],
                    'name': player['name'],
                    'mental_score': player['score']
                }
        
        # For debugging - track matched and unmatched players
        all_matched_players = []
        all_unmatched_players = []
        
        # Process each market
        for market in markets:
            # Reset tracking for this market
            matched_players = []
            unmatched_players = []
            
            # CLEAN SLATE APPROACH: First delete existing recommendations for this market
            cursor.execute('''
            DELETE FROM bet_recommendations 
            WHERE event_name = ? AND market = ?
            ''', (event_name, market))
            
            print(f"Deleted existing recommendations for {event_name}, market {market}")
            
            # Now fetch and process the new data
            api_data = self.fetch_api_data("betting-tools/outrights", {
                "tour": "pga",
                "market": market,
                "odds_format": "decimal"
            })
            
            if not api_data or "odds" not in api_data:
                logger.warning(f"No data returned for {market} market")
                continue
            
            print(f"Processing {len(api_data.get('odds', []))} players for market {market}")
            
            # Process all players in the odds data
            player_odds_list = []
            
            for odds_item in api_data.get("odds", []):
                # Skip if not a dictionary
                if not isinstance(odds_item, dict):
                    continue
                    
                dg_id = str(odds_item.get("dg_id", ""))
                player_name = odds_item.get("player_name", "")
                
                # Try to match player in our database
                player_info = None
                
                if dg_id and dg_id in players_by_dg_id:
                    player_info = players_by_dg_id[dg_id]
                else:
                    # Try name matching as fallback
                    name_parts = player_name.split(' ')
                    if len(name_parts) > 0:
                        last_name = name_parts[-1].lower()
                        if last_name in players_by_name:
                            player_info = players_by_name[last_name]
                
                # If we couldn't match the player, create a placeholder
                if player_info is None:
                    player_info = {
                        'id': None,
                        'name': player_name,
                        'mental_score': None
                    }
                    
                    # Track unmatched player
                    unmatched_players.append(player_name)
                    if player_name not in all_unmatched_players:
                        all_unmatched_players.append(player_name)
                else:
                    # Track matched player
                    matched_players.append(player_name)
                    if player_name not in all_matched_players:
                        all_matched_players.append(player_name)
                
                # Extract model probability
                model_probability = 0
                model_decimal = 0
                model_used = "none"
                
                if "datagolf" in odds_item:
                    datagolf_value = odds_item["datagolf"]
                    
                    if isinstance(datagolf_value, dict):
                        if "baseline_history_fit" in datagolf_value and datagolf_value["baseline_history_fit"]:
                            model_decimal = datagolf_value["baseline_history_fit"]
                            model_probability = 100 / model_decimal if model_decimal > 0 else 0
                            model_used = "baseline_history_fit"
                        elif "baseline" in datagolf_value and datagolf_value["baseline"]:
                            model_decimal = datagolf_value["baseline"]
                            model_probability = 100 / model_decimal if model_decimal > 0 else 0
                            model_used = "baseline"
                    elif isinstance(datagolf_value, (int, float)) and datagolf_value > 0:
                        model_decimal = datagolf_value
                        model_probability = 100 / model_decimal
                        model_used = "unknown"
                
                # Process each sportsbook
                sportsbooks_data = []
                
                for book in ['bet365', 'betmgm', 'bovada', 'draftkings', 'fanduel']:
                    if book in odds_item and odds_item[book]:
                        decimal_odds = odds_item[book]
                        
                        if isinstance(decimal_odds, (int, float)) and decimal_odds > 0:
                            # Calculate base EV
                            base_ev = self.calculate_ev(model_probability, decimal_odds)
                            
                            # Calculate adjusted EV if we have a mental score
                            adjusted_ev = base_ev
                            mental_adjustment = 0
                            
                            if player_info['mental_score'] is not None:
                                adjusted_ev, mental_adjustment = self.calculate_adjusted_ev(
                                    model_probability, 
                                    decimal_odds,
                                    player_info['mental_score'],
                                    market=market
                                )
                            
                            # Store in database
                            self.store_odds_data(
                                player_id=player_info['id'],
                                dg_id=dg_id,
                                player_name=player_name,
                                event_name=event_name,
                                market=market,
                                sportsbook=book,
                                decimal_odds=decimal_odds,
                                model_probability=model_probability,
                                model_used=model_used,
                                base_ev=base_ev,
                                mental_adjustment=mental_adjustment,
                                adjusted_ev=adjusted_ev,
                                mental_score=player_info['mental_score'],
                                conn=conn
                            )
                            
                            # Add to sportsbooks list
                            sportsbooks_data.append({
                                'name': book,
                                'display_name': self._format_sportsbook_name(book),
                                'decimal_odds': decimal_odds,
                                'american_odds': self.decimal_to_american(decimal_odds),
                                'base_ev': base_ev,
                                'mental_adjustment': mental_adjustment,
                                'adjusted_ev': adjusted_ev
                            })
                
                # Add to player odds list if we have any sportsbooks
                if sportsbooks_data:
                    # Sort sportsbooks by adjusted EV
                    sportsbooks_data.sort(key=lambda x: x["adjusted_ev"], reverse=True)
                    
                    player_odds_list.append({
                        'player_id': player_info['id'],
                        'player_name': player_info['name'] or player_name,
                        'dg_id': dg_id,
                        'mental_score': player_info['mental_score'],
                        'model_probability': model_probability,
                        'sportsbooks': sportsbooks_data
                    })
            
            # Debug output for this market
            print(f"Market {market}: Matched {len(matched_players)} players, unmatched {len(unmatched_players)} players")
            
            # Sort players by best adjusted EV
            player_odds_list.sort(
                key=lambda x: max([b["adjusted_ev"] for b in x["sportsbooks"]]) if x["sportsbooks"] else 0, 
                reverse=True
            )
            
            result["markets"][market] = player_odds_list
        
        # Overall stats
        print(f"OVERALL: Matched {len(all_matched_players)} unique players, unmatched {len(all_unmatched_players)} unique players")

        print("\n=== DETAILED UNMATCHED PLAYERS REPORT ===")
        print(f"Total unmatched players: {len(all_unmatched_players)}")
        for name in sorted(all_unmatched_players):
            print(f"  - {name}")
        
        conn.commit()
        conn.close()

        print(f"Total unmatched players: {len(all_unmatched_players)}")
        for name in sorted(all_unmatched_players):
            print(f"  - {name}")
        
        return result
    
    def store_odds_data(self, player_id, dg_id, player_name, event_name, market, sportsbook, 
                    decimal_odds, model_probability, model_used, base_ev, 
                    mental_adjustment, adjusted_ev, mental_score, conn=None):
        """
        Store odds data in the database.
        """
        try:
            # Use the current batch timestamp for consistency
            timestamp = self.current_batch_timestamp
            
            # Determine if we need to create our own connection
            close_conn = False
            if conn is None:
                conn = sqlite3.connect(self.db_path, timeout=30)  # 30 second timeout
                close_conn = True
            
            cursor = conn.cursor()
            
            # First, store raw odds data
            cursor.execute('''
            INSERT INTO odds
            (player_id, dg_id, event_name, market, sportsbook, decimal_odds, 
            model_probability, model_used, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                player_id, dg_id, event_name, market, sportsbook, decimal_odds,
                model_probability, model_used, timestamp
            ))
            
            # Then store the recommendation data
            cursor.execute('''
            INSERT INTO bet_recommendations
            (player_id, event_name, market, sportsbook, decimal_odds, base_ev, 
            mental_adjustment, adjusted_ev, mental_score, model_probability, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                player_id, event_name, market, sportsbook, decimal_odds, 
                base_ev, mental_adjustment, adjusted_ev, mental_score, model_probability, timestamp
            ))
            
            # Only commit and close if we created our own connection
            if close_conn:
                conn.commit()
                conn.close()
            
        except Exception as e:
            logger.error(f"Error storing odds data: {e}")
    
    def decimal_to_american(self, decimal_odds):
        """Convert decimal odds to American format with proper +/- prefix."""
        if decimal_odds >= 2.0:
            american = int(round((decimal_odds - 1) * 100))
            return f"+{american}"  # Add plus prefix for positive odds
        else:
            american = int(round(-100 / (decimal_odds - 1)))
            return f"{american}"  # Negative numbers already include the minus sign

    def _format_market_name(self, market):
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
        return market_display.get(market, market.upper())
    
    def _format_sportsbook_name(self, book):
        """Format sportsbook code into a readable name"""
        book_display = {
            "betmgm": "BetMGM",
            "draftkings": "DraftKings",
            "fanduel": "FanDuel",
            "bet365": "Bet365",
            "bovada": "Bovada",
        }
        return book_display.get(book, book.capitalize())

# Helper function for use in Flask app
def format_market_name(market):
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
    return market_display.get(market, market.upper())