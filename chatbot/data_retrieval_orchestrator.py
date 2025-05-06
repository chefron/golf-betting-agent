import logging
import sqlite3
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger("head_pro.data_retriever")

class DataRetrievalOrchestrator:
    def __init__(self, db_path: str = "data/db/mental_form.db"):
        """Initialize the data retrieval orchestrator."""
        self.db_path = db_path
        self.current_tournament = self._get_current_tournament_name()
        logger.info(f"Initialized data retrieval orchestrator with database: {db_path}")
    
    def retrieve_data(self, query_info: Dict[str, Any]) -> Dict[str, Any]:
        """Orchestrate retrieval of necessary data based on query analysis."""
        logger.info(f"Retrieving data for query type: {query_info.get('query_type', 'unknown')}")
        
        # Initialize the data structure
        data = {
            'query_info': query_info,
            'players': {},
            'tournament': {'name': self.current_tournament},
            'betting_recommendations': [],
            'mental_rankings': {'highest': [], 'lowest': []},
            'tournament_field': [],
            'metadata': {
                'retrieval_timestamp': datetime.now().isoformat()
            }
        }
        
        conn = None
        try:
            # Connect to the database
            conn = self._get_db_connection()
            if not conn:
                logger.error("Failed to connect to database")
                return data
            
            # Process based on query type and data needs
            if query_info.get('needs_player_data', False):
                self._retrieve_player_data(conn, query_info.get('players', []), data)
            
            if query_info.get('needs_betting_recommendations', False):
                self._retrieve_betting_recommendations(conn, data)
            
            if query_info.get('needs_mental_rankings', False):
                self._retrieve_mental_rankings(conn, data)
            
            if query_info.get('needs_tournament_field', False):
                self._retrieve_tournament_field(conn, data)
            
        except Exception as e:
            logger.error(f"Error retrieving data: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            # Ensure connection is closed even if exception occurs
            if conn:
                conn.close()
        
        return data
    
    def _get_current_tournament_name(self) -> str:
        """Get the name of the current tournament."""
        conn = self._get_db_connection()
        if not conn:
            return "Unknown Tournament"
        
        try:
            cursor = conn.cursor()
            cursor.execute('''
            SELECT event_name
            FROM bet_recommendations
            GROUP BY event_name
            ORDER BY MAX(timestamp) DESC
            LIMIT 1
            ''')
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return result[0]
            return "Unknown Tournament"
        except Exception as e:
            logger.error(f"Error getting current tournament: {e}")
            conn.close()
            return "Unknown Tournament"
    
    def _get_db_connection(self) -> Optional[sqlite3.Connection]:
        """Get a connection to the database with better error reporting."""
        try:
            # Check if the database file exists
            import os
            if not os.path.exists(self.db_path):
                logger.error(f"Database file not found: {self.db_path}")
                logger.info(f"Current working directory: {os.getcwd()}")
                return None
                
            # Try to connect
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # This enables column access by name
            
            # Verify connection by executing a simple query
            cursor = conn.cursor()
            cursor.execute("SELECT sqlite_version();")
            version = cursor.fetchone()
            logger.info(f"Connected to database. SQLite version: {version[0]}")
            
            return conn
        except Exception as e:
            logger.error(f"Error connecting to database: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def _retrieve_player_data(self, conn: sqlite3.Connection, player_names: List[str], data: Dict[str, Any]) -> None:
        """Retrieve data for specific players."""
        if not player_names:
            return
        
        for player_name in player_names:
            player = self._find_player_by_name(conn, player_name)
            
            if not player:
                # Player not found
                data['players'][player_name] = {
                    'name': player_name,
                    'not_found': True
                }
                continue
            
            # Get player ID and format display name
            player_id = player['id']
            display_name = self._format_player_name(player['name'])
            
            # Initialize player data
            data['players'][display_name] = {
                'id': player_id,
                'name': player['name'],
                'display_name': display_name,
                'in_field': self._is_player_in_tournament(conn, player_id)
            }
            
            # Add mental form data
            self._add_mental_form_data(conn, player_id, data['players'][display_name])
            
            # Add player personality data
            self._add_player_personality_data(conn, player_id, data['players'][display_name])
            
            # Add odds data for current tournament
            self._add_player_odds_data(conn, player_id, data['players'][display_name])
    
    def _retrieve_betting_recommendations(self, conn: sqlite3.Connection, data: Dict[str, Any]) -> None:
        """Retrieve betting recommendations for the current tournament."""
        cursor = conn.cursor()
        
        # Get recommendations with high EV and good mental form
        cursor.execute('''
        SELECT br.*, p.name as player_name, m.score as mental_score, m.justification as mental_justification
        FROM bet_recommendations br
        JOIN players p ON br.player_id = p.id
        JOIN mental_form m ON p.id = m.player_id
        WHERE br.event_name = ? 
        AND br.adjusted_ev >= 7.0
        AND m.score >= 0.10
        ORDER BY br.adjusted_ev DESC
        LIMIT 15
        ''', (self.current_tournament,))
        
        recommendations = cursor.fetchall()
        
        # Format and add to data
        for rec in recommendations:  # Fixed - use the recommendations variable we already fetched
            rec_dict = dict(rec)
            data['betting_recommendations'].append({
                'player_id': rec_dict['player_id'],
                'player_name': self._format_player_name(rec_dict['player_name']),
                'market': rec_dict['market'],
                'sportsbook': rec_dict['sportsbook'],
                'decimal_odds': rec_dict['decimal_odds'],
                'american_odds': self._format_american_odds(rec_dict['decimal_odds']),
                'adjusted_ev': rec_dict['adjusted_ev'],
                'mental_score': rec_dict['mental_score'],
                'mental_justification': rec_dict['mental_justification']
            })
    
    def _retrieve_mental_rankings(self, conn: sqlite3.Connection, data: Dict[str, Any]) -> None:
        """Retrieve mental form rankings (highest and lowest)."""
        cursor = conn.cursor()
        
        # Get highest mental scores
        cursor.execute('''
        SELECT p.id, p.name, m.score, m.justification, m.last_updated
        FROM players p
        JOIN mental_form m ON p.id = m.player_id
        WHERE m.score > 0
        ORDER BY m.score DESC
        LIMIT 10
        ''')
        
        for player in cursor.fetchall():
            player_dict = dict(player)
            data['mental_rankings']['highest'].append({
                'player_id': player_dict['id'],
                'player_name': self._format_player_name(player_dict['name']),
                'mental_score': player_dict['score'],
                'mental_justification': player_dict['justification'],
                'last_updated': player_dict['last_updated']
            })
        
        # Get lowest mental scores
        cursor.execute('''
        SELECT p.id, p.name, m.score, m.justification, m.last_updated
        FROM players p
        JOIN mental_form m ON p.id = m.player_id
        WHERE m.score < 0
        ORDER BY m.score ASC
        LIMIT 10
        ''')
        
        for player in cursor.fetchall():
            player_dict = dict(player)
            data['mental_rankings']['lowest'].append({
                'player_id': player_dict['id'],
                'player_name': self._format_player_name(player_dict['name']),
                'mental_score': player_dict['score'],
                'mental_justification': player_dict['justification'],
                'last_updated': player_dict['last_updated']
            })
    
    def _retrieve_tournament_field(self, conn: sqlite3.Connection, data: Dict[str, Any]) -> None:
        """Retrieve data about players in the current tournament field with strong mental form."""
        cursor = conn.cursor()
        
        # Get players in the tournament with high mental scores
        cursor.execute('''
        SELECT DISTINCT p.id, p.name, m.score, m.justification
        FROM players p
        JOIN mental_form m ON p.id = m.player_id
        JOIN bet_recommendations br ON p.id = br.player_id
        WHERE br.event_name = ?
        ORDER BY m.score DESC
        LIMIT 10
        ''', (self.current_tournament,))
        
        for player in cursor.fetchall():
            player_dict = dict(player)
            data['tournament_field'].append({
                'player_id': player_dict['id'],
                'player_name': self._format_player_name(player_dict['name']),
                'mental_score': player_dict['score'],
                'mental_justification': player_dict['justification'],
                'in_field': True
            })
    
    def _find_player_by_name(self, conn: sqlite3.Connection, name: str) -> Optional[Dict]:
        """Find a player by name using fuzzy matching."""
        cursor = conn.cursor()
        
        # Try exact match first
        cursor.execute('SELECT * FROM players WHERE name = ?', (name,))
        player = cursor.fetchone()
        if player:
            return dict(player)
        
        # Try case-insensitive match
        cursor.execute('SELECT * FROM players WHERE LOWER(name) = ?', (name.lower(),))
        player = cursor.fetchone()
        if player:
            return dict(player)
        
        # Try to match Last, First format
        name_parts = name.split()
        if len(name_parts) > 1:
            last_name = name_parts[-1]
            first_name = ' '.join(name_parts[:-1])
            reversed_name = f"{last_name}, {first_name}"
            
            cursor.execute('SELECT * FROM players WHERE LOWER(name) = ?', (reversed_name.lower(),))
            player = cursor.fetchone()
            if player:
                return dict(player)
        
        # Try partial match
        cursor.execute('SELECT * FROM players WHERE LOWER(name) LIKE ?', (f"%{name.lower()}%",))
        player = cursor.fetchone()
        if player:
            return dict(player)
        
        # Check special cases mapping
        special_cases = self._get_special_cases_mapping()
        if name.lower() in special_cases:
            mapped_name = special_cases[name.lower()]
            cursor.execute('SELECT * FROM players WHERE LOWER(name) = ?', (mapped_name.lower(),))
            player = cursor.fetchone()
            if player:
                return dict(player)
        
        return None
    
    def _is_player_in_tournament(self, conn: sqlite3.Connection, player_id: int) -> bool:
        """Check if a player is in the current tournament field."""
        cursor = conn.cursor()
        cursor.execute('''
        SELECT 1 FROM bet_recommendations 
        WHERE player_id = ? AND event_name = ? 
        LIMIT 1
        ''', (player_id, self.current_tournament))
        
        return cursor.fetchone() is not None
    
    def _add_mental_form_data(self, conn: sqlite3.Connection, player_id: int, player_data: Dict[str, Any]) -> None:
        """Add mental form data to player info."""
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT score, justification, last_updated
        FROM mental_form
        WHERE player_id = ?
        ''', (player_id,))
        
        mental_form = cursor.fetchone()
        if mental_form:
            mental_form_dict = dict(mental_form)
            player_data['mental_form'] = {
                'score': mental_form_dict['score'],
                'justification': mental_form_dict['justification'],
                'last_updated': mental_form_dict['last_updated']
            }
        else:
            player_data['mental_form'] = None
    
    def _add_player_personality_data(self, conn: sqlite3.Connection, player_id: int, player_data: Dict[str, Any]) -> None:
        """Add personality data to player info."""
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT nicknames, notes
        FROM players
        WHERE id = ?
        ''', (player_id,))
        
        personality = cursor.fetchone()
        if personality:
            personality_dict = dict(personality)
            if personality_dict.get('nicknames'):
                player_data['nicknames'] = personality_dict['nicknames']
            
            if personality_dict.get('notes'):
                player_data['notes'] = personality_dict['notes']
    
    def _add_player_odds_data(self, conn: sqlite3.Connection, player_id: int, player_data: Dict[str, Any]) -> None:
        """Add odds data for player in current tournament."""
        cursor = conn.cursor()
        
        # Initialize odds structure
        player_data['odds'] = {}
        
        # Get odds for common markets
        for market in ['win', 'top_5', 'top_10', 'top_20']:
            cursor.execute('''
            SELECT sportsbook, decimal_odds, adjusted_ev
            FROM bet_recommendations
            WHERE player_id = ? AND event_name = ? AND market = ?
            ORDER BY adjusted_ev DESC
            LIMIT 1
            ''', (player_id, self.current_tournament, market))
            
            best_odds = cursor.fetchone()
            if best_odds:
                best_odds_dict = dict(best_odds)
                player_data['odds'][market] = {
                    'sportsbook': best_odds_dict['sportsbook'],
                    'decimal_odds': best_odds_dict['decimal_odds'],
                    'american_odds': self._format_american_odds(best_odds_dict['decimal_odds']),
                    'adjusted_ev': best_odds_dict['adjusted_ev']
                }
    
    def _format_player_name(self, name: str) -> str:
        """Format player name from 'Last, First' to 'First Last'."""
        if ',' in name:
            parts = name.split(',', 1)
            return f"{parts[1].strip()} {parts[0].strip()}"
        return name
    
    def _format_american_odds(self, decimal_odds: float) -> str:
        """Format decimal odds as American odds string."""
        if decimal_odds >= 2.0:
            american = int(round((decimal_odds - 1) * 100))
            return f"+{american}"
        else:
            american = int(round(-100 / (decimal_odds - 1)))
            return f"{american}"
    
    def _get_special_cases_mapping(self) -> Dict[str, str]:
        """Get mapping of special player name cases."""
        return {
            "scottie": "Scheffler, Scottie",
            "rory": "McIlroy, Rory",
            "rory mac": "McIlroy, Rory",
            "jt": "Thomas, Justin",
            "dj": "Johnson, Dustin",
            "rahm": "Rahm, Jon",
            "xander": "Schauffele, Xander",
            "collin": "Morikawa, Collin",
            "morikawa": "Morikawa, Collin",
            "spieth": "Spieth, Jordan",
            "jordan": "Spieth, Jordan",
            "viktor": "Hovland, Viktor",
            "hovland": "Hovland, Viktor",
            # Add more common nicknames and variations
        }