import sqlite3
import itertools
from typing import List, Dict, Tuple
from datetime import datetime
import os

class DFSLineupOptimizer:
    def __init__(self, db_path: str = "data/db/mental_form.db"):
        self.db_path = db_path
        self.salary_cap = 50000
        self.min_salary = 49000  # Must use at least 98% of cap
        self.lineup_size = 6
        self.min_mental_score = 0.35
        self.max_players_to_consider = 25  # Only consider top 25 by salary
    
    def get_eligible_players(self, event_name: str) -> List[Dict]:
        """Get players with mental score >= 0.35 and DK salary data, ordered by salary"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT 
            p.id as player_id,
            p.name as player_name,
            m.score as mental_score,
            dk.salary as dk_salary
        FROM players p
        JOIN mental_form m ON p.id = m.player_id
        JOIN (
            SELECT player_id, salary
            FROM dfs_projections
            WHERE event_name = ? AND site = 'draftkings' AND slate = 'main'
        ) dk ON p.id = dk.player_id
        WHERE m.score >= ?
        ORDER BY dk.salary DESC
        LIMIT ?
        ''', (event_name, self.min_mental_score, self.max_players_to_consider))
        
        players = []
        for row in cursor.fetchall():
            players.append({
                'player_id': row['player_id'],
                'player_name': row['player_name'],
                'mental_score': row['mental_score'],
                'dk_salary': row['dk_salary']
            })
        
        conn.close()
        return players
    
    def generate_lineups(self, players: List[Dict], max_lineups: int = 10) -> List[Dict]:
        """Generate optimal lineups by brute force combination testing"""
        print(f"Generating lineups from {len(players)} eligible players...")
        
        valid_lineups = []
        total_combinations = 0
        
        # Generate all possible 6-player combinations
        for combo in itertools.combinations(players, self.lineup_size):
            total_combinations += 1
            
            # Calculate total salary and average mental score
            total_salary = sum(player['dk_salary'] for player in combo)
            
            # Skip if under minimum salary threshold
            if total_salary < self.min_salary:
                continue
                
            # Skip if over salary cap
            if total_salary > self.salary_cap:
                continue
            
            # Calculate average mental form score
            avg_mental_score = sum(player['mental_score'] for player in combo) / len(combo)
            
            lineup = {
                'players': combo,
                'total_salary': total_salary,
                'avg_mental_score': avg_mental_score,
                'salary_remaining': self.salary_cap - total_salary
            }
            
            valid_lineups.append(lineup)
        
        print(f"Tested {total_combinations:,} combinations, found {len(valid_lineups)} valid lineups")
        
        # Sort by average mental score (highest first)
        valid_lineups.sort(key=lambda x: x['avg_mental_score'], reverse=True)
        
        return valid_lineups[:max_lineups]
    
    def create_lineups_table(self):
        """Create the optimal_lineups table if it doesn't exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS optimal_lineups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_name TEXT,
            lineup_rank INTEGER,
            player_1_id INTEGER,
            player_2_id INTEGER,
            player_3_id INTEGER,
            player_4_id INTEGER,
            player_5_id INTEGER,
            player_6_id INTEGER,
            total_salary INTEGER,
            avg_mental_score REAL,
            salary_remaining INTEGER,
            generated_at TEXT,
            FOREIGN KEY (player_1_id) REFERENCES players (id),
            FOREIGN KEY (player_2_id) REFERENCES players (id),
            FOREIGN KEY (player_3_id) REFERENCES players (id),
            FOREIGN KEY (player_4_id) REFERENCES players (id),
            FOREIGN KEY (player_5_id) REFERENCES players (id),
            FOREIGN KEY (player_6_id) REFERENCES players (id)
        )
        ''')
        
        # Create index for faster querying
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_optimal_lineups_event 
        ON optimal_lineups(event_name)
        ''')
        
        conn.commit()
        conn.close()
    
    def store_lineups(self, lineups: List[Dict], event_name: str):
        """Store generated lineups in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Clear existing lineups for this event
        cursor.execute('DELETE FROM optimal_lineups WHERE event_name = ?', (event_name,))
        
        # Insert new lineups
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        for rank, lineup in enumerate(lineups, 1):
            # Sort players by salary (highest to lowest) for consistent storage
            sorted_players = sorted(lineup['players'], key=lambda x: x['dk_salary'], reverse=True)
            
            cursor.execute('''
            INSERT INTO optimal_lineups (
                event_name, lineup_rank, 
                player_1_id, player_2_id, player_3_id, 
                player_4_id, player_5_id, player_6_id,
                total_salary, avg_mental_score, salary_remaining, generated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                event_name, rank,
                sorted_players[0]['player_id'], sorted_players[1]['player_id'], 
                sorted_players[2]['player_id'], sorted_players[3]['player_id'],
                sorted_players[4]['player_id'], sorted_players[5]['player_id'],
                lineup['total_salary'], lineup['avg_mental_score'], 
                lineup['salary_remaining'], timestamp
            ))
        
        conn.commit()
        conn.close()
        print(f"Stored {len(lineups)} optimal lineups for {event_name}")
    
    def get_current_tournament(self) -> str:
        """Get the current tournament name from the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT event_name
        FROM tournaments
        ORDER BY last_updated DESC
        LIMIT 1
        ''')
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else "Unknown Tournament"
    
    def optimize_current_tournament(self, max_lineups: int = 5):
        """Main function to optimize lineups for the current tournament"""
        print("=== DFS Lineup Optimizer ===")
        
        # Get current tournament
        event_name = self.get_current_tournament()
        print(f"Optimizing lineups for: {event_name}")
        
        # Create table if needed
        self.create_lineups_table()
        
        # Get eligible players
        players = self.get_eligible_players(event_name)
        
        if not players:
            print(f"No eligible players found (mental score >= {self.min_mental_score})")
            return False
        
        print(f"Found {len(players)} eligible players:")
        for player in players[:10]:  # Show top 10
            print(f"  {player['player_name']}: ${player['dk_salary']:,} (mental: {player['mental_score']:.2f})")
        
        if len(players) > 10:
            print(f"  ... and {len(players) - 10} more")
        
        # Generate optimal lineups
        lineups = self.generate_lineups(players, max_lineups)
        
        if not lineups:
            print("No valid lineups found! Try lowering min_salary threshold.")
            return False
        
        # Display results
        print(f"\nTop {len(lineups)} Optimal Lineups:")
        for i, lineup in enumerate(lineups, 1):
            print(f"\nLineup {i} (Avg Mental: {lineup['avg_mental_score']:.3f}, Salary: ${lineup['total_salary']:,}):")
            for player in sorted(lineup['players'], key=lambda x: x['dk_salary'], reverse=True):
                print(f"  {player['player_name']}: ${player['dk_salary']:,} (mental: {player['mental_score']:.2f})")
        
        # Store in database
        self.store_lineups(lineups, event_name)
        
        return True

def main():
    """Run the lineup optimizer"""
    optimizer = DFSLineupOptimizer()
    success = optimizer.optimize_current_tournament(max_lineups=5)
    
    if success:
        print("\n✅ Lineup optimization completed successfully!")
    else:
        print("\n❌ Lineup optimization failed!")

if __name__ == "__main__":
    main()