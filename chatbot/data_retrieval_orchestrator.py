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
            'tournament_field': {'strongest': [], 'weakest': []},
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

            # Add DFS data for current tournament - ADD THIS LINE
            self._add_player_dfs_data(conn, player_id, data['players'][display_name])

            # Add recent tournament results
            self._add_player_tournament_results(conn, player_id, data['players'][display_name])
    
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
        AND m.score >= 0.25
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
        """Retrieve mental form rankings (highest and lowest) with field status."""
        cursor = conn.cursor()
        
        # Get highest mental scores
        cursor.execute('''
        SELECT p.id, p.name, m.score, m.justification, m.last_updated
        FROM players p
        JOIN mental_form m ON p.id = m.player_id
        WHERE m.score > 0
        ORDER BY m.score DESC
        LIMIT 15
        ''')
        
        for player in cursor.fetchall():
            player_dict = dict(player)
            player_id = player_dict['id']
            
            # Check if player is in the field
            in_field = self._is_player_in_tournament(conn, player_id)
            
            data['mental_rankings']['highest'].append({
                'player_id': player_id,
                'player_name': self._format_player_name(player_dict['name']),
                'mental_score': player_dict['score'],
                'mental_justification': player_dict['justification'],
                'last_updated': player_dict['last_updated'],
                'in_field': in_field
            })
        
        # Get lowest mental scores
        cursor.execute('''
        SELECT p.id, p.name, m.score, m.justification, m.last_updated
        FROM players p
        JOIN mental_form m ON p.id = m.player_id
        WHERE m.score < 0
        ORDER BY m.score ASC
        LIMIT 8
        ''')
        
        for player in cursor.fetchall():
            player_dict = dict(player)
            player_id = player_dict['id']
            
            # Check if player is in the field
            in_field = self._is_player_in_tournament(conn, player_id)
            
            data['mental_rankings']['lowest'].append({
                'player_id': player_id,
                'player_name': self._format_player_name(player_dict['name']),
                'mental_score': player_dict['score'],
                'mental_justification': player_dict['justification'],
                'last_updated': player_dict['last_updated'],
                'in_field': in_field
            })
    
    def _retrieve_tournament_field(self, conn: sqlite3.Connection, data: Dict[str, Any]) -> None:
        """Retrieve data about players in the current tournament field with strong and weak mental form."""
        cursor = conn.cursor()
        
        # Initialize the tournament field structure
        data['tournament_field'] = {'strongest': [], 'weakest': []}
        
        # Get players in the current tournament (distinct player_ids)
        cursor.execute('''
        SELECT DISTINCT player_id
        FROM bet_recommendations
        WHERE event_name = ?
        ''', (self.current_tournament,))
        
        tournament_players = [row[0] for row in cursor.fetchall()]
        print(f"DEBUG: Found {len(tournament_players)} distinct players in the tournament")
        
        if not tournament_players:
            print(f"DEBUG: No players found for tournament: {self.current_tournament}")
            return
        
        # Use a tuple for the IN clause
        player_ids_str = ', '.join('?' for _ in tournament_players)
        
        # Get players with positive mental scores
        cursor.execute(f'''
        SELECT p.id, p.name, m.score, m.justification
        FROM players p
        JOIN mental_form m ON p.id = m.player_id
        WHERE p.id IN ({player_ids_str})
        AND m.score > 0
        ORDER BY m.score DESC
        LIMIT 10
        ''', tournament_players)
        
        # Add strongest players
        for player in cursor.fetchall():
            player_dict = dict(player)
            player_id = player_dict['id']
            player_data = {
                'player_id': player_id,
                'player_name': self._format_player_name(player_dict['name']),
                'mental_score': player_dict['score'],
                'mental_justification': player_dict['justification'],
                'in_field': True,
                'recent_tournaments': []
            }
            
            # Add recent tournament results (limit to 5)
            self._add_player_tournament_results(conn, player_id, player_data, limit=5)
            
            data['tournament_field']['strongest'].append(player_data)
        
        # Get players with negative mental scores
        cursor.execute(f'''
        SELECT p.id, p.name, m.score, m.justification
        FROM players p
        JOIN mental_form m ON p.id = m.player_id
        WHERE p.id IN ({player_ids_str})
        AND m.score < 0
        ORDER BY m.score ASC
        LIMIT 5
        ''', tournament_players)
        
        weak_results = cursor.fetchall()
        print(f"DEBUG: Found {len(weak_results)} players with negative mental scores")
        
        # Add weakest players
        for player in weak_results:
            player_dict = dict(player)
            player_id = player_dict['id']
            player_data = {
                'player_id': player_id,
                'player_name': self._format_player_name(player_dict['name']),
                'mental_score': player_dict['score'],
                'mental_justification': player_dict['justification'],
                'in_field': True,
                'recent_tournaments': []
            }
            
            # Add recent tournament results (limit to 5)
            self._add_player_tournament_results(conn, player_id, player_data, limit=5)
            
            data['tournament_field']['weakest'].append(player_data)
        
        print(f"DEBUG: Added {len(data['tournament_field']['strongest'])} strongest and {len(data['tournament_field']['weakest'])} weakest players")

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
            ''', (player_id, self.current_tournament, market))
            
            odds_results = cursor.fetchall()
            
            if odds_results:
                # Group by decimal odds to find all sportsbooks offering the same price
                odds_by_price = {}
                best_ev = -100  # Track best EV
                best_odds = None
                
                for odds_data in odds_results:
                    odds_dict = dict(odds_data)
                    decimal_odds = odds_dict['decimal_odds']
                    ev = odds_dict['adjusted_ev']
                    
                    # Use rounded decimal odds as key to group similar prices
                    key = round(decimal_odds, 2)
                    
                    if key not in odds_by_price:
                        odds_by_price[key] = {
                            'decimal_odds': decimal_odds,
                            'american_odds': self._format_american_odds(decimal_odds),
                            'adjusted_ev': ev,
                            'sportsbooks': []
                        }
                    
                    odds_by_price[key]['sportsbooks'].append(odds_dict['sportsbook'])
                    
                    # Track best EV
                    if ev > best_ev:
                        best_ev = ev
                        best_odds = key
                
                # Use odds with best EV
                if best_odds is not None:
                    best_data = odds_by_price[best_odds]
                    player_data['odds'][market] = {
                        'sportsbook': ', '.join(best_data['sportsbooks']),
                        'decimal_odds': best_data['decimal_odds'],
                        'american_odds': best_data['american_odds'],
                        'adjusted_ev': best_data['adjusted_ev']
                    }

    def _add_player_dfs_data(self, conn: sqlite3.Connection, player_id: int, player_data: Dict[str, Any]) -> None:
        """Add DFS salary and ownership data to player info."""
        cursor = conn.cursor()
        
        # Get the current tournament name
        event_name = self.current_tournament
        
        # Query for DraftKings data
        cursor.execute('''
        SELECT salary, proj_ownership
        FROM dfs_projections
        WHERE player_id = ? AND event_name = ? AND site = 'draftkings' AND slate = 'main'
        ''', (player_id, event_name))
        
        dk_data = cursor.fetchone()
        
        # Query for FanDuel data
        cursor.execute('''
        SELECT salary
        FROM dfs_projections
        WHERE player_id = ? AND event_name = ? AND site = 'fanduel' AND slate = 'main'
        ''', (player_id, event_name))
        
        fd_data = cursor.fetchone()
        
        # Add DFS data if available
        if dk_data or fd_data:
            player_data['dfs_data'] = {}
            
            # Add salary info
            salary_parts = []
            if dk_data and dk_data[0]:
                salary_parts.append(f"${dk_data[0]} (DraftKings)")
            if fd_data and fd_data[0]:
                salary_parts.append(f"${fd_data[0]} (FanDuel)")
                
            if salary_parts:
                player_data['dfs_data']['salary'] = ", ".join(salary_parts)
            
            # Add ownership info (only available for DraftKings)
            if dk_data and dk_data[1]:
                player_data['dfs_data']['projected_ownership'] = dk_data[1]

    def _add_player_tournament_results(self, conn, player_id, data, limit=10):
        """Add recent tournament results to player data"""
        cursor = conn.cursor()
        
        # Get recent tournament results
        cursor.execute('''
        SELECT event_name, tour, year, finish_position, event_date, course_name
        FROM tournament_results
        WHERE player_id = ?
        ORDER BY event_date DESC
        LIMIT ?
        ''', (player_id, limit))
        
        results = cursor.fetchall()
        
        if results:
            tournaments = []
            for result in results:
                result_dict = dict(result)
                # Format tour to uppercase
                result_dict['tour'] = result_dict.get('tour', '').upper()
                tournaments.append(result_dict)
            
            # Add to player data
            data['recent_tournaments'] = tournaments
    
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
            "JT POSTON": "Poston, J.T.",
            "VICTOR HOVLAND": "Hovland, Viktor",
            "NICOLAI HØJGAARD": "Hojgaard, Nicolai",
            "NIKOLAI HØJGAARD": "Hojgaard, Nicolai",
            "NIKOLAI HOJGAARD": "Hojgaard, Nicolai",
            "RASMUS HØJGAARD": "Hojgaard, Rasmus",
            "AILANO GRILLO": "Grillo, Emiliano",
            "AILANO GRIO": "Grillo, Emiliano",
            "EMILIANO GRIO": "Grillo, Emiliano",
            "CRISTOBAL DEL SOLAR": "Del Solar, Cristobal",
            "WINDHAM CLARK": "Clark, Wyndham",
            "MEN WOO LEE": "Lee, Min Woo",
            "MENWOO LEE": "Lee, Min Woo",
            "MINWOO LEE": "Lee, Min Woo",
            "MINU LEE": "Lee, Min Woo",
            "LUDVIG ÅBERG": "Aberg, Ludvig",
            "LUDVIG OBERG": "Aberg, Ludvig",
            "LUDVIG ÄBERG": "Aberg, Ludvig",
            "STEPHEN JAEGER": "Jaeger, Stephan",
            "STEVEN Jaeger": "Jaeger, Stephan",
            "JJ SPAUN": "Spaun, J.J.",
            "JJ SPAWN": "Spaun, J.J.",
            "CHARLIE HOFFMAN": "Hoffman, Charley",
            "TOM MCKIBBEN": "McKibbin, Tom",
            "ROY MCILROY": "McIlroy, Rory",
            "JOHN RAHM": "Rahm, Jon",
            "JOHN ROM": "Rahm, Jon",
            "HOWTON LEE": "Li, Haotong", 
            "RICKY FOWLER": "Fowler, Rickie",
            "THOMAS DIETRY": "Detry, Thomas",
            "ADRIEN MERONK": "Meronk, Adrian",
            "MAVERICK MCNEELY": "McNealy, Maverick",
            "COLIN MORIKAWA": "Morikawa, Collin",
            "PATRICK ROGERS": "Rodgers, Patrick",
            "WINDAM CLARK": "Clark, Wyndham",
            "ALDRI POTGATER": "Potgieter, Aldrich",
            "JUSTIN SU": "Suh, Justin",
            "RYAN PEAK": "PEAKE, RYAN",
            "JOE HEITH": "Highsmith, Joe",
            "CALLUM HILL": "Hill, Calum",
            "CARL VILIPS": "Vilips, Karl",
            "CARL VILLIPS": "Vilips, Karl",
            "NEIL SHIPLEY": "Shipley, Neal",
            "JOHNNY VEGAS": "Vegas, Jhonattan",
            "BRIAN HARMON": "Harman, Brian",
            "MARK LEISHMAN": "Leishman, Marc",
            "THORBJØRN OLESEN": "Olesen, Thorbjorn",
            "SEBASTIAN MUÑOZ": "Munoz, Sebastian",
            "JOAQUÍN NIEMANN": "Niemann, Joaquin",
            "JOSE LUIS BALLESTER": "Ballester Barrio, Jose Luis",
            "JOSÉ LUIS BALLESTER": "Ballester Barrio, Jose Luis",
            "SCOTTY SCHEFFLER": "Scheffler, Scottie",
            "EMILIO GONZÁLEZ": "Gonzalez, Emilio",
            "JULIÁN ETULAIN": "Etulain, Julian",
            "JORGE FERNÁNDEZ VALDÉS": "Fernandez Valdes, Jorge"
        }