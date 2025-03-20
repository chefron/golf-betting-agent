"""
This module retrieves odds from the DataGolf API for specific players and markets.
"""

import logging
import requests
import os
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('golf.odds_retriever')

load_dotenv()

class OddsRetriever:
    """Retrieves odds from DataGolf API for specific players and markets"""
    
    def __init__(self):
        """
        Initialize the odds retriever.
        """
        # Get API key from environment
        self.api_key = os.getenv('DATAGOLF_API_KEY') or "6e301f31eb610c59de6fa2e57009"
        self.base_url = "https://feeds.datagolf.com"
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
    
    def fetch_relevant_odds(self, player_id, player_name, markets):
        """
        Fetch odds for specific player and markets from DataGolf API.
        
        Args:
            player_id: DataGolf player ID
            player_name: Player name for fallback matching
            markets: List of market types to query
            
        Returns:
            Dictionary of market data for the player
        """
        player_odds = {}
        
        for market in markets:
            logger.info(f"Fetching {market} odds for {player_name}")
            
            # Fetch data for this specific market (using the market name directly)
            api_data = self.fetch_api_data("betting-tools/outrights", {
                "tour": "pga",
                "market": market,
                "odds_format": "decimal"
            })
            
            if not api_data or "odds" not in api_data:
                logger.warning(f"No data returned for {market} market")
                continue
            
            # Find this specific player in the response
            player_data = None
            for odds_item in api_data.get("odds", []):
                # Try to match by ID first, then by name
                if str(odds_item.get("dg_id")) == str(player_id):
                    player_data = odds_item
                    break
                elif odds_item.get("player_name") == player_name:
                    player_data = odds_item
                    break
            
            if not player_data:
                # Try a more lenient name match as fallback
                for odds_item in api_data.get("odds", []):
                    name_parts = player_name.split(", ")
                    if len(name_parts) > 1:
                        last_name = name_parts[0].lower()
                        if last_name in odds_item.get("player_name", "").lower():
                            player_data = odds_item
                            logger.info(f"Found player via last name match: {odds_item.get('player_name')}")
                            break
            
            if not player_data:
                logger.warning(f"Player {player_name} not found in {market} odds data")
                continue
                
            # Extract relevant odds info (model and top sportsbooks)
            market_odds = {
                "market": market,
                "display_name": self._format_market_name(market),
                "model_decimal": 0,
                "model_probability": 0,
                "model_used": "none",
                "sportsbooks": []
            }
            
            # Get model data
            if "datagolf" in player_data:
                if player_data["datagolf"].get("baseline_history_fit"):
                    model_odds = player_data["datagolf"]["baseline_history_fit"]
                    market_odds["model_decimal"] = model_odds
                    market_odds["model_probability"] = 100 / model_odds if model_odds > 0 else 0
                    market_odds["model_used"] = "baseline_history_fit"
                elif player_data["datagolf"].get("baseline"):
                    model_odds = player_data["datagolf"]["baseline"]
                    market_odds["model_decimal"] = model_odds
                    market_odds["model_probability"] = 100 / model_odds if model_odds > 0 else 0
                    market_odds["model_used"] = "baseline"
            
            # Get all available sportsbooks
            target_sportsbooks = [
                'bet365', 'betmgm', 'bovada', 'caesars', 'draftkings', 
                'fanduel', 'pinnacle'
            ]
            
            for book in target_sportsbooks:
                if book in player_data and player_data[book] is not None and player_data[book] > 0:
                    decimal_odds = player_data[book]
                    ev = self.calculate_ev(market_odds["model_probability"], decimal_odds)
                    
                    market_odds["sportsbooks"].append({
                        "name": book,
                        "display_name": self._format_sportsbook_name(book),
                        "odds": decimal_odds,
                        "ev": ev
                    })
            
            # Sort sportsbooks by EV (highest first)
            market_odds["sportsbooks"].sort(key=lambda x: x["ev"], reverse=True)
            
            # Add to player odds if we found any sportsbooks
            if market_odds["sportsbooks"]:
                player_odds[market] = market_odds
                logger.info(f"Found {len(market_odds['sportsbooks'])} sportsbooks with {market} odds for {player_name}")
            else:
                logger.warning(f"No sportsbook odds found for {player_name} in {market} market")
        
        return player_odds
    
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
            "caesars": "Caesars",
            "pinnacle": "Pinnacle",
            "bovada": "Bovada",
        }
        return book_display.get(book, book.capitalize())