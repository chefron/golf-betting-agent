import requests
import pandas as pd
import sqlite3
import json
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns

class GolfBettingTracker:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://feeds.datagolf.com"
        self.db_conn = self._initialize_database()
    
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
            model_probability REAL,  -- Our model's probability
            book_implied_probability REAL,  -- Book's implied probability
            expected_value REAL,  -- EV of the bet (in percentage)
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
        """Fetch Data Golf's pre-tournament model predictions.
        
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
    
    def calculate_kelly_criterion(self, probability, odds, fraction=1.0):
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
        return kelly * fraction
    
    def record_bet(self, event_id, event_name, bet_type, bet_market, player_id, 
                 player_name, odds, stake, model_probability, opponent_id=None, 
                 opponent_name=None, notes=None):
        """Record a new bet in the database"""
        potential_return = stake * odds
        
        # Calculate book implied probability
        book_implied_probability = 1/odds
        
        # Calculate expected value
        win_amount = odds - 1
        expected_value = ((model_probability * win_amount) - ((1 - model_probability) * 1)) * 100
        
        cursor = self.db_conn.cursor()
        cursor.execute('''
        INSERT INTO bets (
            event_id, event_name, bet_type, bet_market, player_id, player_name,
            opponent_id, opponent_name, odds, stake, potential_return, 
            placed_date, outcome, model_probability, 
            book_implied_probability, expected_value, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            event_id, event_name, bet_type, bet_market, player_id, player_name,
            opponent_id, opponent_name, odds, stake, potential_return,
            datetime.now(), 'pending', model_probability,
            book_implied_probability, expected_value, notes
        ))
        
        self.db_conn.commit()
        return cursor.lastrowid
    
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
        
    def close(self):
        """Close database connection"""
        self.db_conn.close()