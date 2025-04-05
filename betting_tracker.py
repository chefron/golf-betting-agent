import requests
import pandas as pd
import sqlite3
import json
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns

class GolfBettingTracker:
    def __init__(self, api_key, kelly_fraction=0.25, default_sportsbook=None):
        self.api_key = api_key
        self.base_url = "https://feeds.datagolf.com"
        self.db_conn = self._initialize_database()
        self.kelly_fraction = kelly_fraction  # Set Kelly fraction during initialization
        self.default_sportsbook = default_sportsbook.lower() if default_sportsbook else None
    
    def _initialize_database(self):
        """Set up SQLite database with necessary tables for tracking bets and results"""
        conn = sqlite3.connect('golf_betting_history.db')
        cursor = conn.cursor()
        
        # Create bets table for storing bet history
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS bets (
            bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT,
            event_name TEXT,
            bet_type TEXT,  -- 'outright', 'matchup', '3-ball', etc.
            bet_market TEXT, -- 'win', 'top_5', 'tournament_matchups', etc.
            player_id INTEGER,
            player_name TEXT,
            opponent_id INTEGER,  -- For matchups
            opponent_name TEXT,   -- For matchups
            odds REAL,
            stake REAL,
            potential_return REAL,
            placed_date TIMESTAMP,
            settled_date TIMESTAMP,
            outcome TEXT,  -- 'win', 'loss', 'void', 'pending'
            profit_loss REAL,
            base_model_probability REAL,  -- DataGolf's original probability
            mental_form_score REAL,  -- Player's mental form score (-1 to 1)
            mental_adjustment REAL,  -- Adjustment percentage
            adjusted_probability REAL,  -- Probability after mental adjustment
            book_implied_probability REAL,  -- Book's implied probability
            expected_value REAL,  -- EV of the bet (in percentage)
            round_num INTEGER,  -- Round number for round-specific bets
            notes TEXT,
            posted_to_twitter INTEGER DEFAULT 0  -- 0=no, 1=yes
        )
        ''')
        
        # Create events table to track tournaments
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            event_name TEXT,
            start_date TEXT,
            end_date TEXT,
            tour TEXT,
            course TEXT,
            status TEXT  -- 'upcoming', 'in_progress', 'completed'
        )
        ''')
        
        # Create performance_metrics table for tracking overall performance
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS performance_metrics (
            metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TIMESTAMP,
            total_bets INTEGER,
            winning_bets INTEGER,
            losing_bets INTEGER,
            pending_bets INTEGER,
            total_staked REAL,
            total_returns REAL,
            profit_loss REAL,
            roi REAL,
            current_bankroll REAL
        )
        ''')
        
        conn.commit()
        return conn
    
    def set_kelly_fraction(self, fraction):
        """Update the Kelly fraction setting
        
        Args:
            fraction: New Kelly fraction value (0-1)
        """
        if 0 <= fraction <= 1:
            self.kelly_fraction = fraction
        else:
            raise ValueError("Kelly fraction must be between 0 and 1")
        
    def set_default_sportsbook(self, sportsbook):
        """Set a default sportsbook to use for all betting recommendations"""
        self.default_sportsbook = sportsbook.lower() if sportsbook else None
        print(f"Default sportsbook set to: {self.default_sportsbook or 'All Sportsbooks'}")
    
    def fetch_current_events(self, tour="pga"):
        """Fetch current tournament information"""
        url = f"{self.base_url}/get-schedule?tour={tour}&key={self.api_key}"
        response = requests.get(url)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching events: {response.status_code}")
            return None
    
    def fetch_betting_odds(self, tour="pga", market="win", odds_format="decimal"):
        """Fetch current outright betting odds for specified market.
        
        Retrieves odds for outright markets like win, top 5, top 10, etc.
        For matchup odds, use fetch_matchup_odds() instead.
        """
        url = f"{self.base_url}/betting-tools/outrights?tour={tour}&market={market}&odds_format={odds_format}&key={self.api_key}"
        response = requests.get(url)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching odds: {response.status_code}")
            return None
    
    def fetch_matchup_odds(self, tour="pga", market="tournament_matchups", odds_format="decimal"):
        """Fetch current matchup betting odds"""
        url = f"{self.base_url}/betting-tools/matchups?tour={tour}&market={market}&odds_format={odds_format}&key={self.api_key}"
        response = requests.get(url)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching matchup odds: {response.status_code}")
            return None
    
    def fetch_model_predictions(self, tour="pga", odds_format="decimal"):
        """Fetch Data Golf's pre-tournament model predictions -- not currently in use but keeping for future development.
        
        Retrieves probabilistic forecasts for the upcoming tournament from Data Golf's
        statistical models. These are the core predictions that are compared against
        bookmaker odds to identify value betting opportunities.
        """
        url = f"{self.base_url}/preds/pre-tournament?tour={tour}&odds_format={odds_format}&key={self.api_key}"
        response = requests.get(url)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching model predictions: {response.status_code}")
            return None
    
    def calculate_kelly_criterion(self, probability, odds):
        """
        Calculate Kelly Criterion for optimal bet sizing
        
        Args:
            probability: Our estimated probability of winning (0-1)
            odds: Decimal odds offered by bookmaker
            fraction: Kelly fraction to reduce variance (0-1)
        
        Returns:
            Recommended stake as fraction of bankroll
        """
        # Decimal odds conversion: b = odds - 1
        b = odds - 1
        
        # Calculate full Kelly stake
        q = 1.0 - probability  # Probability of losing
        
        # Check for edge (only bet when we have positive expected value)
        if (b * probability - q) <= 0:
            return 0
                
        kelly = (b * probability - q) / b
        
        # Apply Kelly fraction to reduce variance
        return kelly * self.kelly_fraction
    
    def process_odds_data(self, odds_data, min_ev_threshold, bankroll, min_stake=1.0):
        """
        Process odds data from OddsRetriever and identify bet opportunities

        Args:
            odds_data: Output from OddsRetriever.update_odds_data()
            min_ev_threshold: Minimum adjusted EV to consider a bet (default 5%)
            bankroll: Current bankroll for bet sizing calculations
            min_stake: Minimum stake to include in recommendations (default $1.0)

        Returns:
            List of bet opportunities sorted by adjusted EV
        """
        event_name = odds_data.get("event_name", "Unknown Event")
        bet_opportunities = []

        high_ev_players = set()
        final_players = set()

        for market_name, market_data in odds_data.get("markets", {}).items():
            if not market_data:
                continue

            for player in market_data:
                player_name = player.get("player_name", "Unknown Player")
                player_id = player.get("player_id")
                mental_score = player.get("mental_score")
                dg_id = player.get("dg_id")

                qualifying_books = []

                for book in player.get("sportsbooks", []):
                    # Filter by sportsbook if a default is set
                    if self.default_sportsbook and book.get("name", "").lower() != self.default_sportsbook:
                        continue

                    adjusted_ev = book.get("adjusted_ev", 0)
                    if adjusted_ev >= min_ev_threshold:
                        qualifying_books.append(book)
                        high_ev_players.add(f"{player_name} - {market_name}")

                if not qualifying_books:
                    continue

                for book in qualifying_books:
                    adjusted_ev = book.get("adjusted_ev", 0)
                    decimal_odds = book.get("decimal_odds", 0)
                    base_model_probability = player.get("model_probability", 0)
                    mental_adjustment = book.get("mental_adjustment", 0)

                    adjustment_factor = 1 + (mental_adjustment / 100)
                    adjusted_probability = base_model_probability * adjustment_factor if base_model_probability > 0 else 0

                    kelly_pct = 0
                    kelly_stake = 0
                    if adjusted_probability > 0:
                        prob_decimal = adjusted_probability / 100
                        kelly_pct = self.calculate_kelly_criterion(prob_decimal, decimal_odds)
                        kelly_stake = kelly_pct * bankroll

                    # Skip opportunities with stakes below the minimum
                    if kelly_stake < min_stake:
                        continue

                    exists, existing_bet = self.has_existing_bet(
                        odds_data.get("event_id", "unknown"),
                        "outright",
                        market_name,
                        player_id
                    )

                    if exists:
                        continue

                    bet_opportunity = {
                        "event_name": event_name,
                        "market": market_name,
                        "player_name": player_name,
                        "player_id": player_id,
                        "dg_id": dg_id,
                        "sportsbook": book.get("name", ""),
                        "decimal_odds": decimal_odds,
                        "american_odds": book.get("american_odds", ""),
                        "base_model_probability": base_model_probability,
                        "mental_form_score": mental_score,
                        "mental_adjustment": mental_adjustment,
                        "adjusted_probability": adjusted_probability,
                        "base_ev": book.get("base_ev", 0),
                        "adjusted_ev": adjusted_ev,
                        "kelly_stake": round(kelly_stake, 2),
                        "kelly_percentage": round(kelly_pct * 100, 2)
                    }

                    bet_opportunities.append(bet_opportunity)
                    final_players.add(f"{player_name} - {market_name}")

        # Optional debug output for filtered players
        filtered_players = high_ev_players - final_players
        if filtered_players:
            print(f"\n=== FILTERED PLAYERS ANALYSIS ===")
            for player_filter in filtered_players:
                player_name, market_name = player_filter.split(" - ")
                for player in market_data:
                    if player.get("player_name") == player_name:
                        print(f"\nPlayer: {player_name}")
                        print("Sportsbook EVs:")
                        for book in player.get("sportsbooks", []):
                            ev = book.get("adjusted_ev", 0)
                            print(f"  {book.get('name')}: {ev:.2f}%")
                        break

        bet_opportunities.sort(key=lambda x: x.get("adjusted_ev", 0), reverse=True)
        return bet_opportunities
    
    def record_bet(self, event_id, event_name, bet_type, bet_market, player_id, 
                player_name, odds, stake, base_model_probability, 
                mental_form_score=None, mental_adjustment=None, adjusted_probability=None,
                opponent_id=None, opponent_name=None, round_num=None, notes=None):
        """Record a new bet in the database"""
        potential_return = stake * odds
        
        # calculate adjusted probability from the base probability and adjustment
        if adjusted_probability is None and base_model_probability is not None and mental_adjustment is not None:
            adjustment_factor = 1 + (mental_adjustment / 100)
            adjusted_probability = base_model_probability * adjustment_factor
        
        # Use the most accurate probability we have for EV calculation
        probability_for_ev = adjusted_probability if adjusted_probability is not None else base_model_probability
        
        # Calculate book implied probability
        book_implied_probability = 1/odds
        
        # Calculate expected value
        win_amount = odds - 1
        expected_value = ((probability_for_ev * win_amount) - ((1 - probability_for_ev) * 1)) * 100
        
        cursor = self.db_conn.cursor()
        cursor.execute('''
        INSERT INTO bets (
            event_id, event_name, bet_type, bet_market, player_id, player_name,
            opponent_id, opponent_name, odds, stake, potential_return, 
            placed_date, outcome, base_model_probability, mental_form_score,
            mental_adjustment, adjusted_probability, book_implied_probability, 
            expected_value, round_num, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            event_id, event_name, bet_type, bet_market, player_id, player_name,
            opponent_id, opponent_name, odds, stake, potential_return,
            datetime.now(), 'pending', base_model_probability, mental_form_score,
            mental_adjustment, adjusted_probability, book_implied_probability,
            expected_value, round_num, notes
        ))
        
        self.db_conn.commit()
        return cursor.lastrowid

    def identify_recommended_bets(self, db_path="data/db/mental_form.db", min_ev=5.0, bankroll=1000, min_stake=1.0, sportsbook=None, max_recommendations=5):
        """
        Identify recommended betting opportunities without recording them
        
        This method:
        1. Fetches odds data using OddsRetriever
        2. Processes the data to identify value betting opportunities
        3. Returns recommended bets without recording them
        
        Args:
            db_path: Path to the mental form database
            min_ev: Minimum adjusted EV to consider a bet (default 5%)
            bankroll: Current bankroll for bet sizing calculations
            min_stake: Minimum stake to include in recommendations (default $1.0)
            sportsbook: Filter to a specific sportsbook (overrides default if specified)
            max_recommendations: Maximum number of recommendations to return
            
        Returns:
            Dictionary with recommended betting opportunities
        """
        from odds_retriever import OddsRetriever
        
        # If a temporary sportsbook override is provided, save the original and set the new one
        original_sportsbook = None
        if sportsbook is not None:
            original_sportsbook = self.default_sportsbook
            self.default_sportsbook = sportsbook.lower() if sportsbook else None
        
        try:
            # Initialize OddsRetriever
            odds_retriever = OddsRetriever(db_path=db_path)
            
            # Get latest odds data with mental adjustments
            odds_data = odds_retriever.update_odds_data()
            
            # Process odds data to find value bets
            bet_opportunities = self.process_odds_data(
                odds_data, 
                min_ev_threshold=min_ev,
                bankroll=bankroll,
                min_stake=min_stake
            )
            
            # Determine which sportsbook(s) were used for display
            sportsbook_display = f"for {self.default_sportsbook.upper()}" if self.default_sportsbook else "across all sportsbooks"
            
            # Print betting opportunities
            print(f"Found {len(bet_opportunities)} potential bets with EV >= {min_ev}% {sportsbook_display}")
            for i, opp in enumerate(bet_opportunities[:max_recommendations]):
                print(f"{i+1}. {opp['player_name']} - {opp['market']} @ {opp['american_odds']} ({opp['sportsbook']})")
                print(f"   Adjusted EV: {opp['adjusted_ev']:.2f}%, Recommended stake: ${opp['kelly_stake']:.2f}")
            
            return {
                "event_name": odds_data.get("event_name", "Unknown Event"),
                "identified_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "sportsbook": self.default_sportsbook,
                "recommendations": bet_opportunities[:max_recommendations],
                "total_opportunities": len(bet_opportunities)
            }
        finally:
            # Restore the original sportsbook if we temporarily changed it
            if original_sportsbook is not None:
                self.default_sportsbook = original_sportsbook

    def place_bets_from_opportunities(self, opportunities, default_stake=None, max_total_stake=None):
        """
        Place bets from identified opportunities
        
        Args:
            opportunities: List of bet opportunities from process_odds_data
            default_stake: Default stake amount (if not using Kelly)
            max_total_stake: Maximum total stake across all bets
            
        Returns:
            List of placed bet IDs
        """
        placed_bet_ids = []
        total_stake = 0
        
        for opp in opportunities:
            # Determine stake - use Kelly if available, otherwise default
            stake = opp.get("kelly_stake") if opp.get("kelly_stake") and not default_stake else default_stake
            
            # Skip if no valid stake
            if not stake or stake <= 0:
                continue
                
            # Check if we'd exceed max total stake
            if max_total_stake and total_stake + stake > max_total_stake:
                # Reduce stake to fit within limit
                stake = max(0, max_total_stake - total_stake)
                if stake <= 0:
                    break
            
            # Place the bet
            bet_id = self.record_bet(
                event_id=opp.get("event_id", "unknown"),
                event_name=opp.get("event_name", "Unknown Event"),
                bet_type="outright",
                bet_market=opp.get("market"),
                player_id=opp.get("player_id"),
                player_name=opp.get("player_name"),
                odds=opp.get("decimal_odds"),
                stake=stake,
                base_model_probability=opp.get("base_model_probability"),
                mental_form_score=opp.get("mental_form_score"),
                mental_adjustment=opp.get("mental_adjustment"),
                adjusted_probability=opp.get("adjusted_probability"),
                notes=f"Book: {opp.get('sportsbook')}, Adj EV: {opp.get('adjusted_ev'):.2f}%"
            )
            
            if bet_id:
                placed_bet_ids.append(bet_id)
                total_stake += stake
        
        return placed_bet_ids
    
    def update_bet_outcome(self, bet_id, outcome, settled_date=None):
        """Update a bet with its outcome (win, loss, void)"""
        if settled_date is None:
            settled_date = datetime.now()
            
        cursor = self.db_conn.cursor()
        
        # Get the bet details first
        cursor.execute("SELECT stake, odds FROM bets WHERE bet_id = ?", (bet_id,))
        bet = cursor.fetchone()
        
        if not bet:
            print(f"Bet ID {bet_id} not found")
            return False
            
        stake, odds = bet
        
        # Calculate profit/loss
        if outcome == 'win':
            profit_loss = stake * (odds - 1)
        elif outcome == 'loss':
            profit_loss = -stake
        elif outcome == 'void':
            profit_loss = 0
        else:
            profit_loss = None
        
        # Update the bet
        cursor.execute('''
        UPDATE bets 
        SET outcome = ?, settled_date = ?, profit_loss = ?
        WHERE bet_id = ?
        ''', (outcome, settled_date, profit_loss, bet_id))
        
        self.db_conn.commit()
        return True
    
    def mark_bet_as_posted(self, bet_id):
        """Mark a bet as posted to Twitter"""
        cursor = self.db_conn.cursor()
        cursor.execute("UPDATE bets SET posted_to_twitter = 1 WHERE bet_id = ?", (bet_id,))
        self.db_conn.commit()
    
    def get_pending_bets(self):
        """Get all pending bets"""
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT * FROM bets WHERE outcome = 'pending'")
        return cursor.fetchall()
    
    def has_existing_bet(self, event_id, bet_type, bet_market, player_id, opponent_id=None, round_num=None, odds_threshold=0.1):
        """
        Check if a similar bet already exists and is still pending
        
        Args:
            event_id: The event ID
            bet_type: Type of bet (outright, matchup, 3ball)
            bet_market: Market (win, top_5, tournament_matchups, etc.)
            player_id: ID of the player
            opponent_id: ID of the opponent (for matchups)
            round_num: Round number for round-specific bets
            odds_threshold: How close the odds need to be to consider it a duplicate (default 10%)
            
        Returns:
            Tuple (exists, existing_bet) where exists is a boolean and existing_bet is the bet data if found
        """
        cursor = self.db_conn.cursor()
        
        # Base query
        query = '''
        SELECT * FROM bets 
        WHERE event_id = ? 
        AND bet_type = ? 
        AND bet_market = ? 
        AND player_id = ?
        AND outcome = 'pending'
        '''
        params = [event_id, bet_type, bet_market, player_id]
        
        # For matchups, also check the opponent
        if bet_type in ['matchup', '3ball'] and opponent_id is not None:
            query += ' AND opponent_id = ?'
            params.append(opponent_id)
        
        # For round-specific bets, check the round number in notes
        if round_num is not None:
            query += " AND round_num = ?"
            params.append(round_num)
        
        # Execute the query
        cursor.execute(query, tuple(params))
        
        existing_bets = cursor.fetchall()
        
        # If no existing bets found, return False
        if not existing_bets:
            return False, None
        
        # Return the first matching bet
        return True, existing_bets[0]
    
    def update_performance_metrics(self, current_bankroll):
        """Update performance metrics table with current stats"""
        cursor = self.db_conn.cursor()
        
        # Get overall betting stats
        cursor.execute('''
        SELECT 
            COUNT(*) as total_bets,
            SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as winning_bets,
            SUM(CASE WHEN outcome = 'loss' THEN 1 ELSE 0 END) as losing_bets,
            SUM(CASE WHEN outcome = 'pending' THEN 1 ELSE 0 END) as pending_bets,
            SUM(stake) as total_staked,
            SUM(CASE WHEN outcome = 'win' THEN potential_return ELSE 0 END) as total_returns,
            SUM(CASE WHEN outcome != 'pending' THEN profit_loss ELSE 0 END) as profit_loss
        FROM bets
        ''')
        
        results = cursor.fetchone()
        
        if results:
            total_bets, winning_bets, losing_bets, pending_bets, total_staked, total_returns, profit_loss = results
            
            # Avoid division by zero
            roi = (profit_loss / total_staked) * 100 if total_staked else 0
            
            cursor.execute('''
            INSERT INTO performance_metrics (
                date, total_bets, winning_bets, losing_bets, pending_bets,
                total_staked, total_returns, profit_loss, roi, current_bankroll
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now(), total_bets, winning_bets, losing_bets, pending_bets,
                total_staked, total_returns, profit_loss, roi, current_bankroll
            ))
            
            self.db_conn.commit()
            return True
        
        return False
    
    def get_betting_history_dataframe(self):
        """Get betting history as a pandas DataFrame"""
        return pd.read_sql_query("SELECT * FROM bets", self.db_conn)
    
    def get_performance_metrics_dataframe(self):
        """Get performance metrics history as a pandas DataFrame"""
        return pd.read_sql_query("SELECT * FROM performance_metrics ORDER BY date", self.db_conn)
    
    def generate_performance_report(self, start_date=None, end_date=None):
        """Generate a comprehensive performance report"""
        bets_df = self.get_betting_history_dataframe()
        
        if start_date:
            bets_df = bets_df[bets_df['placed_date'] >= start_date]
        if end_date:
            bets_df = bets_df[bets_df['settled_date'] <= end_date]
            
        # Filter out pending bets for calculations
        settled_bets = bets_df[bets_df['outcome'] != 'pending']
        
        if settled_bets.empty:
            return {
                "status": "No settled bets in the specified period"
            }
            
        # Calculate key metrics
        total_bets = len(settled_bets)
        winning_bets = len(settled_bets[settled_bets['outcome'] == 'win'])
        win_rate = winning_bets / total_bets if total_bets > 0 else 0
        
        total_stake = settled_bets['stake'].sum()
        total_profit_loss = settled_bets['profit_loss'].sum()
        roi = (total_profit_loss / total_stake) * 100 if total_stake > 0 else 0
        
        # Analyze by bet type
        bet_type_analysis = settled_bets.groupby('bet_type').agg({
            'bet_id': 'count',
            'profit_loss': 'sum',
            'stake': 'sum'
        }).rename(columns={'bet_id': 'count'})
        
        bet_type_analysis['roi'] = (bet_type_analysis['profit_loss'] / bet_type_analysis['stake']) * 100
        
        # Analyze by market type
        market_analysis = settled_bets.groupby('bet_market').agg({
            'bet_id': 'count',
            'profit_loss': 'sum',
            'stake': 'sum'
        }).rename(columns={'bet_id': 'count'})
        
        market_analysis['roi'] = (market_analysis['profit_loss'] / market_analysis['stake']) * 100
        
        report = {
            "total_bets": total_bets,
            "winning_bets": winning_bets,
            "win_rate": win_rate,
            "total_stake": total_stake,
            "total_profit_loss": total_profit_loss,
            "roi": roi,
            "bet_type_analysis": bet_type_analysis.to_dict(),
            "market_analysis": market_analysis.to_dict(),
            "ev_analysis": self._analyze_value_performance(settled_bets)
        }
        
        return report
    
    def _analyze_value_performance(self, bets_df):
        """Analyze performance based on Expected Value (EV)"""
        # Create EV buckets using the proper column
        bets_df['ev_bucket'] = pd.cut(
            bets_df['expected_value'], 
            bins=[-float('inf'), 0, 5, 10, 20, float('inf')],
            labels=['Negative', '0-5%', '5-10%', '10-20%', '20%+']
        )
        
        # Analyze by EV buckets
        ev_analysis = bets_df.groupby('ev_bucket').agg({
            'bet_id': 'count',
            'profit_loss': 'sum',
            'stake': 'sum'
        }).rename(columns={'bet_id': 'count'})
        
        ev_analysis['roi'] = (ev_analysis['profit_loss'] / ev_analysis['stake']) * 100
        
        return ev_analysis.to_dict()
    
    def plot_bankroll_evolution(self, initial_bankroll=1000):
        """Plot bankroll evolution over time"""
        bets_df = self.get_betting_history_dataframe()
        
        # Sort by settled date and filter out pending bets
        settled_bets = bets_df[bets_df['outcome'] != 'pending'].sort_values('settled_date')
        
        if settled_bets.empty:
            print("No settled bets to plot")
            return None
            
        # Calculate cumulative profit/loss
        settled_bets['cumulative_pl'] = settled_bets['profit_loss'].cumsum()
        settled_bets['bankroll'] = initial_bankroll + settled_bets['cumulative_pl']
        
        # Create plot
        plt.figure(figsize=(12, 6))
        plt.plot(settled_bets['settled_date'], settled_bets['bankroll'])
        plt.title('Bankroll Evolution Over Time')
        plt.xlabel('Date')
        plt.ylabel('Bankroll')
        plt.grid(True)
        
        # Save the plot
        plt.savefig('bankroll_evolution.png')
        return 'bankroll_evolution.png'
    
    def plot_ev_vs_roi(self):
        """Plot relationship between Expected Value and actual ROI"""
        bets_df = self.get_betting_history_dataframe()
        settled_bets = bets_df[bets_df['outcome'] != 'pending']
        
        if settled_bets.empty:
            print("No settled bets to plot")
            return None
            
        # Create EV buckets using the proper column
        settled_bets['ev_bucket'] = pd.cut(
            settled_bets['expected_value'], 
            bins=[-float('inf'), 0, 5, 10, 20, float('inf')],
            labels=['Negative', '0-5%', '5-10%', '10-20%', '20%+']
        )
        
        # Calculate ROI by EV bucket
        ev_roi = settled_bets.groupby('ev_bucket').apply(
            lambda x: (x['profit_loss'].sum() / x['stake'].sum()) * 100 if x['stake'].sum() > 0 else 0
        ).reset_index(name='roi')
        
        # Create plot
        plt.figure(figsize=(10, 6))
        sns.barplot(x='ev_bucket', y='roi', data=ev_roi)
        plt.title('ROI by Expected Value (EV) Bucket')
        plt.xlabel('Expected Value')
        plt.ylabel('Actual ROI (%)')
        plt.grid(True, axis='y')
        
        # Save the plot
        plt.savefig('ev_vs_roi.png')
        return 'ev_vs_roi.png'

    def analyze_mental_adjustment_impact(self):
        """
        Analyze how mental form adjustments are affecting betting performance
        
        Returns:
            Dictionary with performance metrics
        """
        cursor = self.db_conn.cursor()
        
        # Get all settled bets with both base and adjusted probabilities
        cursor.execute('''
        SELECT 
            bet_id, player_name, outcome, stake, profit_loss,
            base_model_probability, adjusted_probability, mental_adjustment,
            odds, mental_form_score
        FROM bets 
        WHERE outcome != 'pending'
        AND base_model_probability IS NOT NULL
        AND adjusted_probability IS NOT NULL
        ''')
        
        bets = cursor.fetchall()
        
        if not bets:
            return {"error": "No settled bets with both base and adjusted probabilities"}
        
        # Calculate key metrics
        results = {
            "total_bets": len(bets),
            "winning_bets": sum(1 for bet in bets if bet[2] == 'win'),
            "total_stake": sum(bet[3] for bet in bets),
            "total_profit": sum(bet[4] for bet in bets),
            "positive_adjustments": sum(1 for bet in bets if bet[7] > 0),
            "negative_adjustments": sum(1 for bet in bets if bet[7] < 0),
            "neutral_adjustments": sum(1 for bet in bets if bet[7] == 0),
        }
        
        # ROI calculation
        results["overall_roi"] = (results["total_profit"] / results["total_stake"]) * 100 if results["total_stake"] > 0 else 0
        
        # Group by adjustment direction
        positive_adj_bets = [bet for bet in bets if bet[7] > 0]
        negative_adj_bets = [bet for bet in bets if bet[7] < 0]
        neutral_adj_bets = [bet for bet in bets if bet[7] == 0]
        
        # Calculate ROI by adjustment direction
        results["positive_adj_roi"] = (sum(bet[4] for bet in positive_adj_bets) / sum(bet[3] for bet in positive_adj_bets)) * 100 if positive_adj_bets and sum(bet[3] for bet in positive_adj_bets) > 0 else 0
        results["negative_adj_roi"] = (sum(bet[4] for bet in negative_adj_bets) / sum(bet[3] for bet in negative_adj_bets)) * 100 if negative_adj_bets and sum(bet[3] for bet in negative_adj_bets) > 0 else 0
        results["neutral_adj_roi"] = (sum(bet[4] for bet in neutral_adj_bets) / sum(bet[3] for bet in neutral_adj_bets)) * 100 if neutral_adj_bets and sum(bet[3] for bet in neutral_adj_bets) > 0 else 0
        
        # Analyze by mental form score range
        mental_form_ranges = [
            ('strong_negative', lambda x: x <= -0.5),
            ('moderate_negative', lambda x: -0.5 < x <= -0.2),
            ('neutral', lambda x: -0.2 < x < 0.2),
            ('moderate_positive', lambda x: 0.2 <= x < 0.5),
            ('strong_positive', lambda x: x >= 0.5)
        ]
        
        mental_form_analysis = {}
        for name, condition in mental_form_ranges:
            range_bets = [bet for bet in bets if bet[9] is not None and condition(bet[9])]
            
            if range_bets:
                total_stake = sum(bet[3] for bet in range_bets)
                total_profit = sum(bet[4] for bet in range_bets)
                roi = (total_profit / total_stake) * 100 if total_stake > 0 else 0
                
                mental_form_analysis[name] = {
                    "count": len(range_bets),
                    "stake": total_stake,
                    "profit": total_profit,
                    "roi": roi,
                    "win_rate": sum(1 for bet in range_bets if bet[2] == 'win') / len(range_bets)
                }
        
        results["mental_form_analysis"] = mental_form_analysis
        
        return results
        
    def close(self):
        """Close database connection"""
        self.db_conn.close()