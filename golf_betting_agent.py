import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import argparse
import schedule
import time
import logging
from betting_tracker import GolfBettingTracker
from twitter_automation import GolfBettingTwitterBot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("golf_betting_agent.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("GolfBettingAgent")

class GolfBettingAgent:
    def __init__(self, config_path='config.json'):
        """Initialize the betting agent with configuration"""
        # Load configuration
        self.config = self._load_config(config_path)

        # Initialize the tracker
        self.tracker = GolfBettingTracker(api_key=self.config['data_golf_api_key'])

        # Initialize Twitter bot if enabled
        if self.config['twitter']['enabled']:
            self.twitter_bot = GolfBettingTwitterBot(
                api_key=self.config['twitter']['api_key'],
                api_secret=self.config['twitter']['api_secret'],
                access_token=self.config['twitter']['access_token'],
                access_secret=self.config['twitter']['access_secret']
            )
        else:
            self.twitter_bot = None

        # Set initial bankroll
        self.bankroll = self.config['betting']['initial bankroll']
        self.current_week_bets = 0

        logger.info(f"Golf Betting Agent initialized with {self.bankroll} unit bankroll")

    def _load_config(self, config_path):
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                return config
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {config_path}")
            # Create default configuration
            default_config = {
                "data_golf_api_key": "YOUR_API_KEY_HERE",
                "betting": {
                    "initial_bankroll": 1000,
                    "kelly_fraction": 0.25,
                    "min_ev_percentage": 7.0,
                    "max_bets_per_week": 10,
                    "max_stake_per_bet": 30,
                    "unit_size": 10,
                    "target_tours": ["pga", "euro"],
                    "bet_types": ["outright", "matchup"],
                    "outright_markets": ["win", "top_5", "top_10", "top_20"],
                    "available_sportsbooks": ["draftkings", "fanduel", "betmgm", "caesars", "pointsbet"]
                },
                "twitter": {
                    "enabled": False,
                    "api_key": "YOUR_TWITTER_API_KEY",
                    "api_secret": "YOUR_TWITTER_API_SECRET",
                    "access_token": "YOUR_TWITTER_ACCESS_TOKEN",
                    "access_secret": "YOUR_TWITTER_ACCESS_SECRET",
                    "post_schedule": {
                        "tournament_preview": True,
                        "daily_picks": True,
                        "weekly_recap": True
                    }
                },
                "schedule": {
                    "update_frequency_hours": 12,
                    "performance_update_day": "Monday"
                }
            }
            with open(config_path, 'w') as f:
                json.dump(default_config, f, indent=4)
            logger.info(f"Created default configuration at {config_path}")
            return default_config
    
    def run_daily_update(self):
        """Daily update routine - find value bets and post to Twitter"""
        logger.info("Running daily update")

        # Check for any pending bet results that need to be updated
        self._update_pending_bets()

        # Update performance metrics
        self.tracker.update_performance_metrics(self.bankroll)

        # Find new betting opportunities
        self._find_and_place_bets()

        # Post performance updates on Mondays
        today = datetime.now().strftime("%A")
        if today == self.config['schedule']['performance_update_day']:
            self._post_performance_update()

    def _update_pending_bets(self):
        """Update the status of pending bets -- TO BE IMPLEMENTED LATER"""
        pass

    def _find_and_place_bets(self):
        """Find value bets and place them (i.e., record them as placed)"""
        logger.info("Finding and placing bets")
        
        # Check if we've reached the weekly bet limit
        if self.current_week_bets >= self.config['betting']['max_bets_per_week']:
            logger.info("Weekly bet limit reached, skipping bet placement")
            return
        
        # For each tour, find betting opportunities
        for tour in self.config['betting']['target_tours']:
            # Find outright betting opportunities
            self._find_outright_bets(tour)
            
            # Find matchup betting opportunities
            self._find_matchup_bets(tour)

    def _find_outright_bets(self, tour):
        """Find value in outright betting markets"""
        logger.info(f"Finding outright bets for {tour} tour")

        # First, get model predictions
        model_preds = self.tracker.fetch_model_predictions(tour=tour)

        if not model_preds or 'baseline_history_fit' not in model_preds:
            logger.error(f"Failed to fetch model predictions for {tour}")
            return
        
        # Get predictions from the baseline_history_fit model (which includes course history)
        model_data = {player['player_name']: player for player in model_preds['baseline_history_fit']}

        # For each market we're interested in (win, top 5, etc.)
        for market in self.config['betting']['outright_markets']:
            # Fetch current odds
            odds_data = self.tracker.fetch_betting_odds(tour=tour, market=market)

            if not odds_data or 'odds' not in odds_data:
                logger.error(f"Failed to fetch odds for {tour} {market}")
                continue

            event_name = odds_data.get('event_name', f"{tour.upper()} Event")

            # For each player in the odds
            for player_odds in odds_data['odds']:
                player_name = player_odds['player_name']
                player_id = player_odds['dg_id']
                
                # Skip players not in our model data
                if player_name not in model_data:
                    continue
                
                # Find the best available odds across books the user has access to
                best_odds = 0
                best_book = None

                for book in player_odds:
                    # Check if this is a sportsbook (not metadata) and available to the user
                    if (book not in ['player_name', 'dg_id', 'datagolf'] and 
                        book in self.config['betting']['available_sportsbooks']):
                        if player_odds[book] and player_odds[book] > best_odds:
                            best_odds = player_odds[book]
                            best_book = book
                
                if not best_book:
                    continue

                # Get model probability for this market
                model_prob = model_data[player_name].get(market, 0)
                if not model_prob:
                    continue

                # Convert decimal probability to percentage
                model_prob_pct = model_prob * 100
                
                # Calculate implied probability from odds
                implied_prob = (1 / best_odds) * 100
                
                # Calculate EV (Expected Value)
                win_amount = best_odds - 1
                ev_percentage = ((model_prob_pct/100 * win_amount) - ((1 - model_prob_pct/100) * 1)) * 100

                # If EV exceeds our minimum threshold
                min_ev = self.config['betting']['min_ev_percentage']
                if ev_percentage > min_ev:
                    # Calculate Kelly stake
                    raw_kelly = self.tracker.calculate_kelly_criterion(
                        model_prob_pct / 100, 
                        best_odds,
                        self.config['betting']['kelly_fraction']
                    )

                    # Calculate the actual stake amount based on Kelly, capped by maximum stake
                    raw_kelly_amount = raw_kelly * self.bankroll
                    stake = min(raw_kelly_amount, self.config['betting']['max_stake_per_bet'])

                    # Skip bets that are too small (less than $1)
                    if stake < 1.0:
                        continue

                    # Calculate wager in units for reporting purposes
                    units = stake / self.config['betting']['unit_size']

