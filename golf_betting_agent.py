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
        self.bankroll = self.config['betting']['initial_bankroll']
        self.current_week_wagered = 0.0

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
                    "max_weekly_wagering_amount": 250,
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
        if self.current_week_wagered >= self.config['betting']['max_weekly_wagering_amount']:
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

        # First, get current events to identify the event ID
        schedule_data = self.tracker.fetch_current_events(tour=tour)
        if not schedule_data or 'schedule' not in schedule_data:
            logger.error(f"Failed to fetch schedule for {tour}")
            return
        
        # Find the current/upcoming event
        current_date = datetime.now().strftime("%Y-%m-%d")
        current_event = None
        for event in schedule_data['schedule']:
            # Find event that's starting now or in the near future
            if event['start_date'] >= current_date:
                current_event = event
                break
        
        if not current_event:
            logger.error(f"No upcoming events found for {tour}")
            return
        
        event_id = current_event['event_id']
        event_name = current_event['event_name']

        # Get model predictions
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

                    # Add a check to ensure we don't exceed weekly wagering limit
                    if self.current_week_wagered + stake > self.config['betting']['max_weekly_wagering_amount']:
                        remaining = self.config['betting']['max_weekly_wagering_amount'] - self.current_week_wagered
                        if remaining < 1.0:
                            logger.info("Weekly wagering limit reached, skipping bet")
                            continue
                        logger.info(f"Adjusting stake from ${stake:.2f} to ${remaining:.2f} to stay within weekly limit")
                        stake = remaining

                    # Skip bets that are too small (less than $1)
                    if stake < 1.0:
                        continue

                    # Calculate wager in units for reporting purposes
                    units = stake / self.config['betting']['unit_size']

                    # Place the bet
                    bet_id = self.tracker.record_bet(
                        event_id=event_id,
                        event_name=event_name,
                        bet_type='outright',
                        bet_market=market,
                        player_id=player_id,
                        player_name=player_name,
                        odds=best_odds,
                        stake=stake,
                        model_probability=model_prob_pct / 100,
                        notes=f"Book: {best_book}, Units: {units:.2f}, Kelly: {raw_kelly:.4f}"
                    )

                    logger.info(f"Placed {stake:.2f} unit bet on {player_name} to {market} at {best_odds} odds (EV: {ev_percentage:.2f}%)")

                    # Post to Twitter if enabled
                    if self.twitter_bot and self.config['twitter']['enabled'] and self.config['twitter']['post_schedule']['daily_picks']:
                        bet_data = {
                            'event_name': event_name,
                            'player_name': player_name,
                            'bet_type': 'outright',
                            'bet_market': market,
                            'odds': best_odds,
                            'probability': model_prob_pct,
                            'stake': stake
                        }
                        
                        try:
                            tweet_text = self.twitter_bot.post_outright_bet(bet_data)
                            self.tracker.mark_bet_as_posted(bet_id)
                            logger.info(f"Posted bet {bet_id} to Twitter")
                        except Exception as e:
                            logger.error(f"Failed to post to Twitter: {e}")
                    
                    # After placing the bet, increment the wager amount
                    self.current_week_wagered += stake
                    
                    # Check if we've hit our weekly limit
                    if self.current_week_wagered >= self.config['betting']['max_weekly_wagering_amount']:
                        logger.info(f"Weekly wagering limit of ${self.config['betting']['max_weekly_wagering_amount']:.2f} reached")
                        return

    def _find_matchup_bets(self, tour):
        """Find value in matchup betting markets"""
        logger.info(f"Finding matchup bets for {tour} tour")
        
        # First, get current events to identify the event ID
        schedule_data = self.tracker.fetch_current_events(tour=tour)
        if not schedule_data or 'schedule' not in schedule_data:
            logger.error(f"Failed to fetch schedule for {tour}")
            return
        
        # Find the current/upcoming event
        current_date = datetime.now().strftime("%Y-%m-%d")
        current_event = None
        for event in schedule_data['schedule']:
            # Find event that's starting now or in the near future
            if event['start_date'] >= current_date:
                current_event = event
                break
        
        if not current_event:
            logger.error(f"No upcoming events found for {tour}")
            return
        
        event_id = current_event['event_id']
        event_name = current_event['event_name']
        
        # Fetch matchup odds
        matchup_odds = self.tracker.fetch_matchup_odds(tour=tour, market="tournament_matchups")
        
        if not matchup_odds or 'match_list' not in matchup_odds:
            logger.error(f"Failed to fetch matchup odds for {tour}")
            return
        
        # For each matchup
        for matchup in matchup_odds['match_list']:
            # Extract player info
            p1_name = matchup['p1_player_name']
            p1_id = matchup['p1_dg_id']
            p2_name = matchup['p2_player_name']
            p2_id = matchup['p2_dg_id']
            
            # Get Data Golf's model probability
            if 'datagolf' in matchup['odds']:
                dg_p1_odds = matchup['odds']['datagolf'].get('p1', 0)
                if dg_p1_odds > 0:
                    dg_p1_prob = 1 / dg_p1_odds
                else:
                    continue
            else:
                continue
            
            # Find best odds for player 1 from sportsbooks the user has access to
            best_p1_odds = 0
            best_p1_book = None
            
            for book in matchup['odds']:
                if (book != 'datagolf' and 
                    book in self.config['betting']['available_sportsbooks'] and
                    'p1' in matchup['odds'][book] and 
                    matchup['odds'][book]['p1'] is not None and 
                    matchup['odds'][book]['p1'] > 0):
                    
                    if matchup['odds'][book]['p1'] > best_p1_odds:
                        best_p1_odds = matchup['odds'][book]['p1']
                        best_p1_book = book
            
            # Calculate EV for player 1
            if best_p1_book:
                p1_implied_prob = 1 / best_p1_odds
                
                # Calculate EV for player 1
                p1_win_amount = best_p1_odds - 1
                p1_ev_percentage = ((dg_p1_prob * p1_win_amount) - ((1 - dg_p1_prob) * 1)) * 100
                
                min_ev = self.config['betting']['min_ev_percentage']
                if p1_ev_percentage > min_ev:
                    # Calculate Kelly stake
                    raw_kelly = self.tracker.calculate_kelly_criterion(
                        dg_p1_prob, 
                        best_p1_odds,
                        self.config['betting']['kelly_fraction']
                    )
                    
                    # Calculate the actual stake amount based on Kelly, capped by maximum stake
                    raw_kelly_amount = raw_kelly * self.bankroll
                    stake = min(raw_kelly_amount, self.config['betting']['max_stake_per_bet'])

                    # Add a check to ensure we don't exceed weekly wagering limit
                    if self.current_week_wagered + stake > self.config['betting']['max_weekly_wagering_amount']:
                        remaining = self.config['betting']['max_weekly_wagering_amount'] - self.current_week_wagered
                        if remaining < 1.0:
                            logger.info("Weekly wagering limit reached, skipping bet")
                            continue
                        logger.info(f"Adjusting stake from ${stake:.2f} to ${remaining:.2f} to stay within weekly limit")
                        stake = remaining
                    
                    # Skip bets that are too small (less than $1)
                    if stake < 1.0:
                        continue
                    
                    # Calculate units for reporting
                    units = stake / self.config['betting']['unit_size']
                    
                    # Place the bet
                    bet_id = self.tracker.record_bet(
                        event_id=event_id,
                        event_name=event_name,
                        bet_type='matchup',
                        bet_market='tournament_matchups',  # Plural to match the API
                        player_id=p1_id,
                        player_name=p1_name,
                        opponent_id=p2_id,
                        opponent_name=p2_name,
                        odds=best_p1_odds,
                        stake=stake,
                        model_probability=dg_p1_prob,
                        notes=f"Book: {best_p1_book}, Kelly: {raw_kelly:.4f}, Units: {units:.2f}"
                    )
                    
                    logger.info(f"Placed {stake:.2f} unit bet on {p1_name} over {p2_name} at {best_p1_odds} odds (EV: {p1_ev_percentage:.2f}%)")
                    
                    # Post to Twitter if enabled
                    if self.twitter_bot and self.config['twitter']['enabled'] and self.config['twitter']['post_schedule']['daily_picks']:
                        bet_data = {
                            'event_name': event_name,
                            'player_name': p1_name,
                            'opponent_name': p2_name,
                            'bet_type': 'matchup',
                            'odds': best_p1_odds,
                            'probability': dg_p1_prob * 100,
                            'stake': stake
                        }
                        
                        try:
                            tweet_text = self.twitter_bot.post_matchup_bet(bet_data)
                            self.tracker.mark_bet_as_posted(bet_id)
                            logger.info(f"Posted matchup bet {bet_id} to Twitter")
                        except Exception as e:
                            logger.error(f"Failed to post to Twitter: {e}")
                    
                    # After placing the bet, increment the wager amount
                    self.current_week_wagered += stake
                    
                    # Check if we've hit our weekly limit
                    if self.current_week_wagered >= self.config['betting']['max_weekly_wagering_amount']:
                        logger.info(f"Weekly wagering limit of ${self.config['betting']['max_weekly_wagering_amount']:.2f} reached")
                        return
            
            # Find best odds for player 2 from sportsbooks the user has access to
            best_p2_odds = 0
            best_p2_book = None
            
            for book in matchup['odds']:
                if (book != 'datagolf' and 
                    book in self.config['betting']['available_sportsbooks'] and
                    'p2' in matchup['odds'][book] and 
                    matchup['odds'][book]['p2'] is not None and 
                    matchup['odds'][book]['p2'] > 0):
                    
                    if matchup['odds'][book]['p2'] > best_p2_odds:
                        best_p2_odds = matchup['odds'][book]['p2']
                        best_p2_book = book
            
            # Calculate EV for player 2
            if best_p2_book:
                dg_p2_prob = 1 - dg_p1_prob  # Probability for player 2
                p2_implied_prob = 1 / best_p2_odds
                
                # Calculate EV for player 2
                p2_win_amount = best_p2_odds - 1
                p2_ev_percentage = ((dg_p2_prob * p2_win_amount) - ((1 - dg_p2_prob) * 1)) * 100
                
                min_ev = self.config['betting']['min_ev_percentage']
                if p2_ev_percentage > min_ev:
                    # Calculate Kelly stake
                    raw_kelly = self.tracker.calculate_kelly_criterion(
                        dg_p2_prob, 
                        best_p2_odds,
                        self.config['betting']['kelly_fraction']
                    )
                    
                    # Calculate the actual stake amount based on Kelly, capped by maximum stake
                    raw_kelly_amount = raw_kelly * self.bankroll
                    stake = min(raw_kelly_amount, self.config['betting']['max_stake_per_bet'])
                    
                    # Skip bets that are too small (less than $1)
                    if stake < 1.0:
                        continue
                    
                    # Calculate units for reporting
                    units = stake / self.config['betting']['unit_size']
                    
                    # Place the bet
                    bet_id = self.tracker.record_bet(
                        event_id=event_id,
                        event_name=event_name,
                        bet_type='matchup',
                        bet_market='tournament_matchups',  # Plural to match the API
                        player_id=p2_id,
                        player_name=p2_name,
                        opponent_id=p1_id,
                        opponent_name=p1_name,
                        odds=best_p2_odds,
                        stake=stake,
                        model_probability=dg_p2_prob,
                        notes=f"Book: {best_p2_book}, Kelly: {raw_kelly:.4f}, Units: {units:.2f}"
                    )
                    
                    logger.info(f"Placed {stake:.2f} unit bet on {p2_name} over {p1_name} at {best_p2_odds} odds (EV: {p2_ev_percentage:.2f}%)")
                    
                    # Post to Twitter if enabled
                    if self.twitter_bot and self.config['twitter']['enabled'] and self.config['twitter']['post_schedule']['daily_picks']:
                        bet_data = {
                            'event_name': event_name,
                            'player_name': p2_name,
                            'opponent_name': p1_name,
                            'bet_type': 'matchup',
                            'odds': best_p2_odds,
                            'probability': dg_p2_prob * 100,
                            'stake': stake
                        }
                        
                        try:
                            tweet_text = self.twitter_bot.post_matchup_bet(bet_data)
                            self.tracker.mark_bet_as_posted(bet_id)
                            logger.info(f"Posted matchup bet {bet_id} to Twitter")
                        except Exception as e:
                            logger.error(f"Failed to post to Twitter: {e}")
                    
                    # After placing the bet, increment the wager amount
                    self.current_week_wagered += stake
                    
                    # Check if we've hit our weekly limit
                    if self.current_week_wagered >= self.config['betting']['max_weekly_wagering_amount']:
                        logger.info("Weekly bet limit reached")
                        return

    def _post_performance_update(self):
        """Post performance update to Twitter"""
        logger.info("Posting performance update")
        
        if not self.twitter_bot or not self.config['twitter']['enabled'] or not self.config['twitter']['post_schedule']['weekly_recap']:
            logger.info("Twitter posting disabled or weekly recap disabled")
            return
        
        # Generate performance report
        report = self.tracker.generate_performance_report()
        
        # Generate bankroll evolution chart
        chart_path = self.tracker.plot_bankroll_evolution(self.config['betting']['initial_bankroll'])
        
        if report and chart_path:
            try:
                self.twitter_bot.post_performance_update(report, chart_path)
                logger.info(f"Posted performance update to Twitter")
            except Exception as e:
                logger.error(f"Failed to post performance update: {e}")

    def reset_weekly_wager_counter(self):
        """Reset the weekly wagered amount - called every Monday"""
        if self.current_week_wagered > 0:
            logger.info(f"Resetting weekly wagered amount from ${self.current_week_wagered:.2f} to $0.00")
        else:
            logger.info("Resetting weekly wagered amount")
        self.current_week_wagered = 0.0

def main():
    """Run the golf betting agent"""
    parser = argparse.ArgumentParser(description='Golf Betting Agent')
    parser.add_argument('--config', type=str, default='config.json', help='Path to configuration file')
    parser.add_argument('--run-once', action='store_true', help='Run once and exit')
    args = parser.parse_args()
    
    # Initialize the agent
    agent = GolfBettingAgent(config_path=args.config)
    
    if args.run_once:
        agent.run_daily_update()
        return
    
    # Schedule daily updates
    schedule.every(agent.config['schedule']['update_frequency_hours']).hours.do(agent.run_daily_update)
    
    # Reset weekly wager counter every Monday
    schedule.every().monday.at("00:01").do(agent.reset_weekly_wager_counter)
    
    logger.info("Golf betting agent scheduled, running continuously")
    
    # Run continuously
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    main()