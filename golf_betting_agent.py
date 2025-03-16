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
                    "matchup_markets": ["tournament_matchups", "round_matchups", "3_balls"],
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
        """Find value in outright betting markets using DataGolf's model odds from the betting endpoint"""
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

        # For each market we're interested in (win, top 5, etc.)
        for market in self.config['betting']['outright_markets']:
            # Fetch current odds (which includes the DataGolf model predictions)
            odds_data = self.tracker.fetch_betting_odds(tour=tour, market=market)

            if not odds_data or 'odds' not in odds_data:
                logger.error(f"Failed to fetch odds for {tour} {market}")
                continue

            logger.info(f"Processing {market} market for {odds_data.get('event_name', event_name)}")

            # For each player in the odds
            for player_odds in odds_data['odds']:
                player_name = player_odds['player_name']
                player_id = player_odds['dg_id']
                
                # Get model odds directly from this response
                if 'datagolf' not in player_odds or not player_odds['datagolf']:
                    continue
                
                # Prefer baseline_history_fit model if available
                if player_odds['datagolf']['baseline_history_fit'] is not None:
                    model_odds = player_odds['datagolf']['baseline_history_fit']
                elif player_odds['datagolf']['baseline'] is not None:
                    model_odds = player_odds['datagolf']['baseline']
                else:
                    # Skip if no model odds available
                    continue
                
                # Convert decimal odds to probability
                model_prob = 1 / model_odds
                
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

                # Calculate implied probability from odds
                implied_prob = 1 / best_odds
                
                # Calculate EV (Expected Value)
                win_amount = best_odds - 1
                ev_percentage = ((model_prob * win_amount) - ((1 - model_prob) * 1)) * 100

                # Log high EV values for inspection
                if ev_percentage > 50:
                    logger.info(f"High EV detected for {player_name} {market}: {ev_percentage:.2f}%. Model prob: {model_prob:.4f} ({model_odds}), Book odds: {best_odds}")
                    
                # If EV exceeds our minimum threshold
                min_ev = self.config['betting']['min_ev_percentage']
                if ev_percentage > min_ev:
                    # Calculate Kelly stake
                    raw_kelly = self.tracker.calculate_kelly_criterion(
                        model_prob,
                        best_odds,
                        self.config['betting']['kelly_fraction']
                    )

                    # Calculate the stake in units, capped by maximum stake per bet
                    raw_kelly_amount = raw_kelly * self.bankroll  # This is in dollars
                    kelly_units = raw_kelly_amount / self.config['betting']['unit_size']  # Convert to units
                    max_units = self.config['betting']['max_stake_per_bet'] / self.config['betting']['unit_size']
                    units = min(kelly_units, max_units)  # Cap in units

                    # Convert units back to dollars for weekly limit check and database
                    stake = units * self.config['betting']['unit_size']

                    # Skip bets that are too small (less than 0.1 units)
                    if units < 0.1:
                        continue

                    logger.info(f"Kelly calculation for {player_name} {market}: raw_kelly={raw_kelly:.4f}, " +
                    f"kelly_amount=${raw_kelly_amount:.2f}, kelly_units={kelly_units:.2f}")

                    # Add a check to ensure we don't exceed weekly wagering limit
                    if self.current_week_wagered + stake > self.config['betting']['max_weekly_wagering_amount']:
                        remaining = self.config['betting']['max_weekly_wagering_amount'] - self.current_week_wagered
                        if remaining < self.config['betting']['unit_size'] * 0.1:  # Less than 0.1 units
                            logger.info("Weekly wagering limit reached, skipping bet")
                            continue
                        logger.info(f"Adjusting stake from ${stake:.2f} to ${remaining:.2f} to stay within weekly limit")
                        stake = remaining
                        units = stake / self.config['betting']['unit_size']

                    # Check if a similar bet already exists
                    exists, existing_bet = self.tracker.has_existing_bet(
                        event_id=event_id,
                        bet_type='outright',
                        bet_market=market,
                        player_id=player_id,
                        round_num=None  # No round for outright bets
                    )
                    
                    if exists:
                        logger.info(f"Similar bet already exists for {player_name} to {market} - skipping")
                        continue

                    logger.info(f"Final stake for {player_name} {market}: units={units:.2f}, stake=${stake:.2f}, " +
                    f"max_units={max_units:.2f}, max_stake=${self.config['betting']['max_stake_per_bet']:.2f}")

                    # Place the bet with units calculation already done
                    bet_id = self.tracker.record_bet(
                        event_id=event_id,
                        event_name=event_name,
                        bet_type='outright',
                        bet_market=market,
                        player_id=player_id,
                        player_name=player_name,
                        odds=best_odds,
                        stake=stake,  # This is in dollars
                        model_probability=model_prob,
                        round_num=None,
                        notes=f"Book: {best_book}, Units: {units:.2f}, Kelly: {raw_kelly:.4f}, Model odds: {model_odds}"
                    )

                    logger.info(f"Placed {units:.2f} unit bet on {player_name} to {market} at {best_odds} odds (EV: {ev_percentage:.2f}%) with {best_book}")

                    # Post to Twitter if enabled
                    if self.twitter_bot and self.config['twitter']['enabled'] and self.config['twitter']['post_schedule']['daily_picks']:
                        bet_data = {
                            'event_name': event_name,
                            'player_name': player_name,
                            'bet_type': 'outright',
                            'bet_market': market,
                            'odds': best_odds,
                            'probability': model_prob * 100,  # Convert to percentage for display
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
        
        # Define the matchup markets to check
        matchup_markets = self.config['betting'].get('matchup_markets', ['tournament_matchups', 'round_matchups', '3_balls'])
        
        # For each matchup market type
        for market_type in matchup_markets:
            logger.info(f"Checking {market_type} for {tour} tour")
            
            # Fetch matchup odds for this market type
            matchup_odds = self.tracker.fetch_matchup_odds(tour=tour, market=market_type)
            
            if not matchup_odds:
                logger.error(f"Failed to fetch {market_type} odds for {tour}")
                continue
            
            # Check if there's a match_list in the response
            if 'match_list' not in matchup_odds:
                logger.error(f"No match_list in {market_type} response. Keys: {list(matchup_odds.keys())}")
                continue
            
            # Check if match_list is a string (message) rather than a list of matchups
            if isinstance(matchup_odds['match_list'], str):
                logger.info(f"No {market_type} available: {matchup_odds['match_list']}")
                continue
            
            # If we have actual matchups, proceed with processing them
            # Get any additional info from the response
            round_num = matchup_odds.get('round_num', None)
            
            # For each matchup
            for matchup in matchup_odds['match_list']:
                try:
                    # Check if this is a 3-ball or a 2-player matchup
                    is_3ball = market_type == '3_balls' or 'p3_player_name' in matchup
                    
                    # Extract player info
                    p1_name = matchup['p1_player_name']
                    p1_id = matchup['p1_dg_id']
                    p2_name = matchup['p2_player_name']
                    p2_id = matchup['p2_dg_id']
                    
                    # For 3-balls, also get player 3 info
                    p3_name = matchup.get('p3_player_name', None) if is_3ball else None
                    p3_id = matchup.get('p3_dg_id', None) if is_3ball else None
                    
                    # Get Data Golf's model odds
                    if 'odds' in matchup and 'datagolf' in matchup['odds']:
                        dg_odds = matchup['odds']['datagolf']
                        dg_p1_odds = dg_odds.get('p1')
                        
                        # Skip if no model odds available
                        if not dg_p1_odds or dg_p1_odds <= 0:
                            continue
                        
                        # Convert odds to probability
                        dg_p1_prob = 1 / dg_p1_odds
                        
                        # For 3-balls, calculate probabilities differently
                        if is_3ball:
                            dg_p2_odds = dg_odds.get('p2')
                            dg_p3_odds = dg_odds.get('p3')
                            
                            # Skip if missing odds for any player
                            if not dg_p2_odds or not dg_p3_odds or dg_p2_odds <= 0 or dg_p3_odds <= 0:
                                continue
                                
                            # Convert to probabilities
                            dg_p2_prob = 1 / dg_p2_odds
                            dg_p3_prob = 1 / dg_p3_odds
                            
                            # Normalize probabilities to sum to 1
                            total_prob = dg_p1_prob + dg_p2_prob + dg_p3_prob
                            dg_p1_prob = dg_p1_prob / total_prob
                            dg_p2_prob = dg_p2_prob / total_prob
                            dg_p3_prob = dg_p3_prob / total_prob
                        else:
                            # For 2-player matchups
                            dg_p2_prob = 1 - dg_p1_prob
                    else:
                        continue
                    
                    # Process each player in the matchup
                    players_info = [
                        {'id': p1_id, 'name': p1_name, 'prob': dg_p1_prob, 'opponent_id': p2_id, 'opponent_name': p2_name},
                        {'id': p2_id, 'name': p2_name, 'prob': dg_p2_prob, 'opponent_id': p1_id, 'opponent_name': p1_name}
                    ]
                    
                    # Add player 3 for 3-balls
                    if is_3ball and p3_name and p3_id:
                        players_info.append({'id': p3_id, 'name': p3_name, 'prob': dg_p3_prob, 'opponent_id': None, 'opponent_name': f"{p1_name} & {p2_name}"})
                    
                    # Process each player in the matchup
                    for player in players_info:
                        # Find best odds for this player from available sportsbooks
                        best_odds = 0
                        best_book = None
                        
                        # Player index (p1, p2, p3)
                        player_idx = f"p{players_info.index(player) + 1}"
                        
                        for book in matchup['odds']:
                            if (book != 'datagolf' and 
                                book in self.config['betting']['available_sportsbooks'] and
                                player_idx in matchup['odds'][book] and 
                                matchup['odds'][book][player_idx] is not None and 
                                matchup['odds'][book][player_idx] > 0):
                                
                                if matchup['odds'][book][player_idx] > best_odds:
                                    best_odds = matchup['odds'][book][player_idx]
                                    best_book = book
                        
                        # Calculate EV if we found odds
                        if best_book and best_odds > 0:
                            implied_prob = 1 / best_odds
                            
                            # Calculate EV
                            win_amount = best_odds - 1
                            ev_percentage = ((player['prob'] * win_amount) - ((1 - player['prob']) * 1)) * 100
                            
                            # Check if EV exceeds our threshold
                            min_ev = self.config['betting']['min_ev_percentage']
                            if ev_percentage > min_ev:
                                # Calculate Kelly stake
                                raw_kelly = self.tracker.calculate_kelly_criterion(
                                    player['prob'], 
                                    best_odds,
                                    self.config['betting']['kelly_fraction']
                                )
                                
                                # Calculate the stake in units, capped by maximum stake per bet
                                raw_kelly_amount = raw_kelly * self.bankroll  # This is in dollars
                                kelly_units = raw_kelly_amount / self.config['betting']['unit_size']  # Convert to units
                                max_units = self.config['betting']['max_stake_per_bet'] / self.config['betting']['unit_size']
                                units = min(kelly_units, max_units)  # Cap in units

                                # Convert units back to dollars for weekly limit check and database
                                stake = units * self.config['betting']['unit_size']

                                # Log Kelly calculation details
                                logger.info(f"Kelly calculation for {player['name']} in {market_type}: raw_kelly={raw_kelly:.4f}, kelly_amount=${raw_kelly_amount:.2f}, kelly_units={kelly_units:.2f}")
                                logger.info(f"Final stake for {player['name']} in {market_type}: units={units:.2f}, stake=${stake:.2f}, max_units={max_units:.2f}, max_stake=${self.config['betting']['max_stake_per_bet']:.2f}")

                                # Skip bets that are too small (less than 0.1 units)
                                if units < 0.1:
                                    continue
                                
                                # Add a check to ensure we don't exceed weekly wagering limit
                                if self.current_week_wagered + stake > self.config['betting']['max_weekly_wagering_amount']:
                                    remaining = self.config['betting']['max_weekly_wagering_amount'] - self.current_week_wagered
                                    if remaining < self.config['betting']['unit_size'] * 0.1:  # Less than 0.1 units
                                        logger.info("Weekly wagering limit reached, skipping bet")
                                        continue
                                    logger.info(f"Adjusting stake from ${stake:.2f} to ${remaining:.2f} to stay within weekly limit")
                                    stake = remaining
                                    units = stake / self.config['betting']['unit_size']

                                # Check if a similar bet already exists
                                exists, existing_bet = self.tracker.has_existing_bet(
                                    event_id=event_id,
                                    bet_type='matchup' if not is_3ball else '3ball',
                                    bet_market=market_type,
                                    player_id=player['id'],
                                    opponent_id=player['opponent_id'],
                                    round_num=round_num
                                )
                                
                                if exists:
                                    logger.info(f"Similar bet already exists for {player['name']} vs {player['opponent_name']} - skipping")
                                    continue
                                
                                # Format bet details for logging and notes
                                if is_3ball:
                                    bet_desc = f"{player['name']} to win 3-ball"
                                    if round_num:
                                        bet_desc += f" (Round {round_num})"
                                else:
                                    bet_desc = f"{player['name']} over {player['opponent_name']}"
                                    if market_type == 'round_matchups' and round_num:
                                        bet_desc += f" (Round {round_num})"
                                
                                # Place the bet
                                bet_id = self.tracker.record_bet(
                                    event_id=event_id,
                                    event_name=event_name,
                                    bet_type='matchup' if not is_3ball else '3ball',
                                    bet_market=market_type,
                                    player_id=player['id'],
                                    player_name=player['name'],
                                    opponent_id=player['opponent_id'],
                                    opponent_name=player['opponent_name'],
                                    odds=best_odds,
                                    stake=stake,
                                    model_probability=player['prob'],
                                    round_num=round_num,
                                    notes=f"Book: {best_book}, Units: {units:.2f}, Kelly: {raw_kelly:.4f}, Market: {market_type}"
                                )
                                
                                logger.info(f"Placed {units:.2f} unit bet on {bet_desc} at {best_odds} odds (EV: {ev_percentage:.2f}%) with {best_book}")
                                
                                # Post to Twitter if enabled
                                if self.twitter_bot and self.config['twitter']['enabled'] and self.config['twitter']['post_schedule']['daily_picks']:
                                    bet_data = {
                                        'event_name': event_name,
                                        'player_name': player['name'],
                                        'opponent_name': player['opponent_name'],
                                        'bet_type': 'matchup' if not is_3ball else '3ball',
                                        'market_type': market_type,
                                        'round': round_num,
                                        'odds': best_odds,
                                        'probability': player['prob'] * 100,  # Convert to percentage for display
                                        'stake': stake
                                    }
                                    
                                    try:
                                        tweet_text = self.twitter_bot.post_matchup_bet(bet_data)
                                        self.tracker.mark_bet_as_posted(bet_id)
                                        logger.info(f"Posted matchup bet {bet_id} to Twitter")
                                    except Exception as e:
                                        logger.error(f"Failed to post to Twitter: {e}")
                                
                                # Update wagered amount
                                self.current_week_wagered += stake
                                
                                # Check weekly limit
                                if self.current_week_wagered >= self.config['betting']['max_weekly_wagering_amount']:
                                    logger.info(f"Weekly wagering limit of ${self.config['betting']['max_weekly_wagering_amount']:.2f} reached")
                                    return
                        
                except Exception as e:
                    logger.error(f"Error processing matchup in {market_type}: {e}")
                    logger.debug(f"Problematic matchup data: {matchup}")
                    continue

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