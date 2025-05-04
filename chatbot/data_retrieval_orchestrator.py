"""
Data Retrieval Orchestrator for the Head Pro Chatbot

This module orchestrates the retrieval of specific data from the golf database
based on the query analysis, organizing it into a structured format for the response generator.
"""

import logging
import sqlite3
import os
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("head_pro.data_retriever")

class DataRetrievalOrchestrator:
    def __init__(self, db_path: str = "../data/db/mental_form.db"):
        """
        Initialize the data retrieval orchestrator.
        
        Args:
            db_path: Path to the SQLite database
        """
        self.db_path = db_path
        logger.info(f"Initialized data retrieval orchestrator with database: {db_path}")
    
    def retrieve_data(self, query_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Orchestrate retrieval of all necessary data based on query analysis.
        
        Args:
            query_info: The query analysis results
            
        Returns:
            Dictionary containing all retrieved data organized by type
        """
        logger.info(f"Retrieving data for query type: {query_info.get('query_type', 'unknown')}")
        
        # Initialize the data structure
        data = {
            'query_info': query_info,
            'players': {},
            'tournaments': {},
            'odds': {},
            'recommendations': [],
            'metadata': {
                'retrieval_timestamp': datetime.now().isoformat(),
                'data_current_as_of': datetime.now().isoformat()
            }
        }
        
        conn = None
        try:
            # Connect to the database
            conn = self._get_db_connection()
            if not conn:
                logger.error("Failed to connect to database")
                return data
            
            # Process players - either specified in query or get relevant ones
            self._process_players(conn, query_info, data)
            
            # Process tournaments - get current tournament info
            self._process_tournaments(conn, query_info, data)
            
            # Get odds data if needed
            if query_info.get('needs_odds_data', False) or query_info.get('is_betting_related', False):
                self._retrieve_odds_data(conn, query_info, data)
            
            # Get betting recommendations if appropriate
            if query_info.get('query_type') == 'betting_value':
                self._retrieve_betting_recommendations(conn, query_info, data)
            
        except Exception as e:
            logger.error(f"Error retrieving data: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            # Ensure connection is closed even if exception occurs
            if conn:
                conn.close()
        
        return data
    
    def _get_db_connection(self) -> Optional[sqlite3.Connection]:
        """
        Get a connection to the database.
        
        Returns:
            SQLite connection object or None if connection fails
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # This enables column access by name
            return conn
        except Exception as e:
            logger.error(f"Error connecting to database: {e}")
            return None
    
    def _process_players(self, conn: sqlite3.Connection, query_info: Dict[str, Any], data: Dict[str, Any]) -> None:
        """Process players from the query info with improved relevance filtering."""
        player_names = query_info.get('players', [])
        
        # Get current tournament
        tournament = self._get_current_tournament(conn)
        tournament_name = tournament.get('event_name') if tournament else None
        
        # First process specifically requested players
        specific_player_ids = []
        for player_name in player_names:
            # Try different variations for common players
            if player_name.lower() == 'scottie':
                player_name = 'Scottie Scheffler'
            elif player_name.lower() == 'rory':
                player_name = 'Rory McIlroy'
            # Add more common nickname mappings
            
            player = self._find_player_by_name(conn, player_name)
            if player:
                player_id = player['id']
                specific_player_ids.append(player_id)
                
                db_player_name = player['name']
                display_name = self._format_player_name(db_player_name)
                
                # Add player info
                data['players'][display_name] = {
                    'id': player_id,
                    'name': db_player_name,
                    'display_name': display_name,
                    'in_field': self._is_player_in_tournament(conn, player_id, tournament_name)
                }
                
                # For specific players, always include mental form and personality if available
                self._add_mental_form_data(conn, player_id, data['players'][display_name])
                self._add_player_personality_data(conn, player_id, data['players'][display_name])
                
            else:
                # Track not found players
                data['players'][player_name] = {
                    'id': None,
                    'name': player_name,
                    'display_name': player_name,
                    'not_found': True
                }
        
        # If no specific players or in mental_form/betting_value queries, add relevant context
        if not specific_player_ids or query_info.get('query_type') in ['mental_form', 'betting_value']:
            # Get players in the current tournament
            if tournament_name:
                tournament_players = self._get_players_in_tournament(conn, tournament_name, limit=10)
                
                # Process tournament players
                for player in tournament_players:
                    player_id = player['id']
                    # Skip if already added
                    if player_id in specific_player_ids:
                        continue
                    
                    db_player_name = player['name']
                    display_name = self._format_player_name(db_player_name)
                    
                    # Add player info
                    data['players'][display_name] = {
                        'id': player_id,
                        'name': db_player_name,
                        'display_name': display_name,
                        'in_field': True
                    }
                    
                    # Add mental form if needed
                    if query_info.get('needs_mental_form', False):
                        self._add_mental_form_data(conn, player_id, data['players'][display_name])

    def _is_player_in_tournament(self, conn: sqlite3.Connection, player_id: int, tournament_name: str) -> bool:
        """Check if a player is in the field for the current tournament."""
        if not tournament_name:
            return False
        
        cursor = conn.cursor()
        
        # Check betting recommendations for this player and tournament
        cursor.execute('''
        SELECT 1 FROM bet_recommendations 
        WHERE player_id = ? AND event_name = ? 
        LIMIT 1
        ''', (player_id, tournament_name))
        
        return cursor.fetchone() is not None
    
    def _get_players_in_tournament(self, conn: sqlite3.Connection, tournament_name: str, limit: int = 10) -> List[Dict]:
        """
        Get players participating in the current tournament, prioritizing those with high mental
        scores and strong betting value.
        
        Args:
            conn: Database connection
            tournament_name: Tournament name
            limit: Maximum number of players to return
            
        Returns:
            List of player dictionaries
        """
        cursor = conn.cursor()
        
        # First prioritize players with high mental scores AND high EV
        cursor.execute('''
        SELECT DISTINCT p.id, p.name, m.score, MAX(b.adjusted_ev) as max_ev
        FROM players p
        JOIN bet_recommendations b ON p.id = b.player_id
        JOIN mental_form m ON p.id = m.player_id
        WHERE b.event_name = ? 
        AND m.score > 0.25 
        AND b.adjusted_ev > 7.0
        GROUP BY p.id
        ORDER BY max_ev DESC
        LIMIT ?
        ''', (tournament_name, limit))
        
        results = cursor.fetchall()
        
        # If we didn't get enough results, add players with high mental scores
        if len(results) < limit:
            remaining = limit - len(results)
            existing_ids = [r['id'] for r in results]
            
            # Add players with high mental scores
            if existing_ids:
                id_list = ','.join('?' for _ in existing_ids)
                query = f'''
                SELECT DISTINCT p.id, p.name, m.score, MAX(b.adjusted_ev) as max_ev
                FROM players p
                JOIN bet_recommendations b ON p.id = b.player_id
                JOIN mental_form m ON p.id = m.player_id
                WHERE b.event_name = ? 
                AND m.score > 0.25
                AND p.id NOT IN ({id_list})
                GROUP BY p.id
                ORDER BY m.score DESC
                LIMIT ?
                '''
                params = [tournament_name] + existing_ids + [remaining]
            else:
                query = '''
                SELECT DISTINCT p.id, p.name, m.score, MAX(b.adjusted_ev) as max_ev
                FROM players p
                JOIN bet_recommendations b ON p.id = b.player_id
                JOIN mental_form m ON p.id = m.player_id
                WHERE b.event_name = ? 
                AND m.score > 0.25
                GROUP BY p.id
                ORDER BY m.score DESC
                LIMIT ?
                '''
                params = [tournament_name, remaining]
                
            cursor.execute(query, params)
            results.extend(cursor.fetchall())
        
        # If we still don't have enough, add players with high EVs
        if len(results) < limit:
            remaining = limit - len(results)
            existing_ids = [r['id'] for r in results]
            
            if existing_ids:
                id_list = ','.join('?' for _ in existing_ids)
                query = f'''
                SELECT DISTINCT p.id, p.name, m.score, MAX(b.adjusted_ev) as max_ev
                FROM players p
                JOIN bet_recommendations b ON p.id = b.player_id
                LEFT JOIN mental_form m ON p.id = m.player_id
                WHERE b.event_name = ? 
                AND b.adjusted_ev > 7.0
                AND p.id NOT IN ({id_list})
                GROUP BY p.id
                ORDER BY max_ev DESC
                LIMIT ?
                '''
                params = [tournament_name] + existing_ids + [remaining]
            else:
                query = '''
                SELECT DISTINCT p.id, p.name, m.score, MAX(b.adjusted_ev) as max_ev
                FROM players p
                JOIN bet_recommendations b ON p.id = b.player_id
                LEFT JOIN mental_form m ON p.id = m.player_id
                WHERE b.event_name = ? 
                AND b.adjusted_ev > 7.0
                GROUP BY p.id
                ORDER BY max_ev DESC
                LIMIT ?
                '''
                params = [tournament_name, remaining]
                
            cursor.execute(query, params)
            results.extend(cursor.fetchall())
        
        return [dict(player) for player in results]
    
    def _process_tournaments(self, conn: sqlite3.Connection, query_info: Dict[str, Any], data: Dict[str, Any]) -> None:
        """
        Process tournaments from the query info.
        
        Args:
            conn: Database connection
            query_info: Query analysis info
            data: Data structure to populate
        """
        # We only support the current tournament
        current_tournament = self._get_current_tournament(conn)
        
        if current_tournament:
            tournament_name = current_tournament['event_name']
            data['tournaments'][tournament_name] = current_tournament
        else:
            logger.warning("No current tournament found in database")
            data['tournaments']['unknown'] = {
                'name': 'Unknown Tournament',
                'not_found': True
            }
    
    def _get_top_ranked_players(self, conn: sqlite3.Connection, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get top ranked players based on the absolute value of their mental form score.
        
        Args:
            conn: Database connection
            limit: Maximum number of players to return
            
        Returns:
            List of player info dictionaries
        """
        cursor = conn.cursor()
        
        # Get players with mental form data, ordered by absolute value of score
        cursor.execute('''
        SELECT p.id, p.name, p.dg_id, p.amateur, p.country, m.score
        FROM players p
        JOIN mental_form m ON p.id = m.player_id
        WHERE m.score IS NOT NULL
        ORDER BY ABS(m.score) DESC
        LIMIT ?
        ''', (limit,))
        
        players = cursor.fetchall()
        return [dict(player) for player in players]
    
    def _add_player_personality_data(self, conn: sqlite3.Connection, player_id: int, player_data: Dict[str, Any]) -> None:
        """
        Add personality data (nicknames, notes) to the player info.
        
        Args:
            conn: Database connection
            player_id: Player ID
            player_data: Player data dictionary to update
        """
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT nicknames, notes
        FROM players
        WHERE id = ?
        ''', (player_id,))
        
        personality = cursor.fetchone()
        if personality:
            if personality['nicknames']:
                player_data['nicknames'] = personality['nicknames']
            
            if personality['notes']:
                player_data['notes'] = personality['notes']
    
    def _get_current_tournament(self, conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
        """
        Get the current tournament from the database.
        
        Args:
            conn: Database connection
            
        Returns:
            Tournament info dictionary or None if not found
        """
        cursor = conn.cursor()
        
        # Get the most recent tournament from bet_recommendations
        cursor.execute('''
        SELECT event_name, MAX(timestamp) as latest
        FROM bet_recommendations
        GROUP BY event_name
        ORDER BY latest DESC
        LIMIT 1
        ''')
        
        tournament = cursor.fetchone()
        if tournament:
            return {
                'event_name': tournament['event_name'],
                'timestamp': tournament['latest']
            }
        
        return None
    
    def _get_odds_for_market(self, conn: sqlite3.Connection, tournament_name: str, market: str, 
                            player_ids: List[int] = None) -> List[Dict[str, Any]]:
        """
        Get odds data for a specific market, tournament, and optionally filtered by player IDs.
        Only includes odds data where the player has a mental form score.
        
        Args:
            conn: Database connection
            tournament_name: Tournament name
            market: Market name (win, top_5, etc.)
            player_ids: Optional list of player IDs to filter by
            
        Returns:
            List of odds data dictionaries
        """
        cursor = conn.cursor()
        
        # Base query
        query = '''
        SELECT br.id, br.player_id, p.name as player_name, 
               br.sportsbook, br.decimal_odds, br.base_ev,
               br.mental_adjustment, br.adjusted_ev, br.mental_score,
               br.model_probability, br.timestamp
        FROM bet_recommendations br
        JOIN players p ON br.player_id = p.id
        WHERE br.event_name = ? 
              AND br.market = ?
              AND br.mental_score IS NOT NULL
        '''
        
        params = [tournament_name, market]
        
        # Add player filter if provided
        if player_ids:
            placeholders = ','.join('?' for _ in player_ids)
            query += f" AND br.player_id IN ({placeholders})"
            params.extend(player_ids)
        
        # Add ordering and limit
        query += " ORDER BY br.adjusted_ev DESC"
        
        cursor.execute(query, params)
        odds_data = cursor.fetchall()
        
        # Format odds data
        formatted_odds = []
        for odds in odds_data:
            odds_dict = dict(odds)
            
            # Add formatted American odds
            decimal_odds = odds_dict.get('decimal_odds', 0)
            if decimal_odds >= 2.0:
                american_odds = f"+{int(round((decimal_odds - 1) * 100))}"
            else:
                american_odds = f"{int(round(-100 / (decimal_odds - 1)))}"
            
            odds_dict['american_odds'] = american_odds
            
            # Add display name
            player_name = odds_dict.get('player_name', '')
            odds_dict['player_display_name'] = self._format_player_name(player_name)
            
            formatted_odds.append(odds_dict)
        
        return formatted_odds
    
    def _get_value_bets(self, conn: sqlite3.Connection, tournament_name: str, market: str, 
                    min_ev: float = 7.0, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get value bets for a specific market and tournament.
        Only includes bets where the player has a mental form score.
        
        Args:
            conn: Database connection
            tournament_name: Tournament name
            market: Market name (win, top_5, etc.)
            min_ev: Minimum adjusted EV to consider
            limit: Maximum number of bets to return
            
        Returns:
            List of value bet dictionaries
        """
        cursor = conn.cursor()
        
        query = '''
        SELECT br.id, br.player_id, p.name as player_name, 
            br.sportsbook, br.decimal_odds, br.base_ev,
            br.mental_adjustment, br.adjusted_ev, br.mental_score,
            br.model_probability, br.timestamp
        FROM bet_recommendations br
        JOIN players p ON br.player_id = p.id
        WHERE br.event_name = ? 
            AND br.market = ? 
            AND br.adjusted_ev >= ?
            AND br.mental_score IS NOT NULL  -- Explicitly require mental score
        ORDER BY br.adjusted_ev DESC
        LIMIT ?
        '''
        
        cursor.execute(query, (tournament_name, market, min_ev, limit))
        bets = cursor.fetchall()
        
        # Format value bets
        formatted_bets = []
        for bet in bets:
            bet_dict = dict(bet)
            
            # Add formatted American odds
            decimal_odds = bet_dict.get('decimal_odds', 0)
            if decimal_odds >= 2.0:
                american_odds = f"+{int(round((decimal_odds - 1) * 100))}"
            else:
                american_odds = f"{int(round(-100 / (decimal_odds - 1)))}"
            
            bet_dict['american_odds'] = american_odds
            
            # Add display name
            player_name = bet_dict.get('player_name', '')
            bet_dict['player_display_name'] = self._format_player_name(player_name)
            
            formatted_bets.append(bet_dict)
        
        return formatted_bets
    
    def _find_player_by_name(self, conn: sqlite3.Connection, name: str) -> Optional[Dict[str, Any]]:
        """
        Find a player by name with fuzzy matching.
        
        Args:
            conn: Database connection
            name: Player name to search for
            
        Returns:
            Player info dictionary or None if not found
        """
        cursor = conn.cursor()
        
        # Convert input name to lowercase for comparison
        name_lower = name.lower()
        name_parts = name_lower.split()
        
        if len(name_parts) > 1:
            # First try an exact match with reversed name (last, first)
            last_name = name_parts[-1]
            first_name = ' '.join(name_parts[:-1])
            reversed_name = f"{last_name}, {first_name}"
            
            cursor.execute('SELECT * FROM players WHERE LOWER(name) = ?', (reversed_name,))
            players = cursor.fetchall()
            if players:
                return dict(players[0])
            
            # If that fails, try to find players with matching last name
            cursor.execute('SELECT * FROM players WHERE LOWER(name) LIKE ?', (f"%{last_name},%",))
            players = cursor.fetchall()
            
            # For common last names, we need to check if the first name also matches
            if players:
                # Check if any of these players have a matching first name
                for player in players:
                    player_name_parts = player['name'].lower().split(', ')
                    if len(player_name_parts) > 1:
                        player_first = player_name_parts[1]
                        # Check if input first name is in player's first name
                        if first_name in player_first or player_first in first_name:
                            return dict(player)
        
        # Try a simple contains match as fallback
        cursor.execute('SELECT * FROM players WHERE LOWER(name) LIKE ?', (f"%{name_lower}%",))
        players = cursor.fetchall()
        if players:
            return dict(players[0])
        
        # Check special cases mapping
        special_cases = self._get_special_cases_mapping()
        if name_lower in special_cases:
            mapped_name = special_cases[name_lower]
            cursor.execute('SELECT * FROM players WHERE LOWER(name) = ?', (mapped_name.lower(),))
            players = cursor.fetchall()
            if players:
                return dict(players[0])
        
        return None
    
    def _add_mental_form_data(self, conn: sqlite3.Connection, player_id: int, player_data: Dict[str, Any]) -> None:
        """
        Add mental form data to the player info.
        
        Args:
            conn: Database connection
            player_id: Player ID
            player_data: Player data dictionary to update
        """
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT score, justification, last_updated
        FROM mental_form
        WHERE player_id = ?
        ''', (player_id,))
        
        mental_form = cursor.fetchone()
        if mental_form:
            player_data['mental_form'] = {
                'score': mental_form['score'],
                'justification': mental_form['justification'],
                'last_updated': mental_form['last_updated']
            }
        else:
            player_data['mental_form'] = {
                'score': None,
                'justification': "No mental form data available.",
                'last_updated': None
            }
    
    def _add_player_insights(self, conn: sqlite3.Connection, player_id: int, player_data: Dict[str, Any], limit: int = 10) -> None:
        """
        Add recent insights to the player info.
        
        Args:
            conn: Database connection
            player_id: Player ID
            player_data: Player data dictionary to update
            limit: Maximum number of insights to include
        """
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT text, source, source_type, content_title, content_url, date
        FROM insights
        WHERE player_id = ?
        ORDER BY date DESC
        LIMIT ?
        ''', (player_id, limit))
        
        insights = cursor.fetchall()
        player_data['insights'] = [dict(insight) for insight in insights]
    
    def _retrieve_odds_data(self, conn: sqlite3.Connection, query_info: Dict[str, Any], data: Dict[str, Any]) -> None:
        """
        Retrieve odds data for specified players and tournaments.
        
        Args:
            conn: Database connection
            query_info: Query analysis info
            data: Data structure to populate
        """
        markets = query_info.get('markets', [])
        if not markets:
            markets = ['win', 'top_5', 'top_10']  # Default markets
            
        player_ids = []
        
        # Get relevant player IDs
        for player_info in data['players'].values():
            if player_info.get('id'):
                player_ids.append(player_info['id'])
        
        # Get the tournaments
        tournament_names = list(data['tournaments'].keys())
        
        # Initialize odds structure
        data['odds'] = {
            'by_player': {},
            'by_tournament': {},
            'by_market': {}
        }
        
        if not player_ids or not tournament_names:
            logger.warning("No players or tournaments for odds retrieval")
            return
        
        # Get odds data for each tournament, player, and market
        for tournament_name in tournament_names:
            data['odds']['by_tournament'][tournament_name] = {}
            
            for market in markets:
                # Format market for SQL query
                db_market = market.replace(" ", "_").replace("-", "_").lower()
                
                # Get odds for all players in this tournament and market
                market_odds = self._get_odds_for_market(
                    conn, tournament_name, db_market, player_ids
                )
                
                # Organize by market
                if db_market not in data['odds']['by_market']:
                    data['odds']['by_market'][db_market] = {}
                
                data['odds']['by_market'][db_market][tournament_name] = market_odds
                
                # Organize by tournament
                data['odds']['by_tournament'][tournament_name][db_market] = market_odds
                
                # Organize by player
                for player_odds in market_odds:
                    player_id = player_odds.get('player_id')
                    if player_id:
                        # Find display name for this player ID
                        display_name = None
                        for player_name, player_info in data['players'].items():
                            if player_info.get('id') == player_id:
                                display_name = player_name
                                break
                        
                        if display_name:
                            if display_name not in data['odds']['by_player']:
                                data['odds']['by_player'][display_name] = {}
                            
                            if tournament_name not in data['odds']['by_player'][display_name]:
                                data['odds']['by_player'][display_name][tournament_name] = {}
                            
                            data['odds']['by_player'][display_name][tournament_name][db_market] = player_odds
    
    def _retrieve_betting_recommendations(self, conn: sqlite3.Connection, query_info: Dict[str, Any], data: Dict[str, Any]) -> None:
        """
        Retrieve betting recommendations based on odds and mental form.
        
        Args:
            conn: Database connection
            query_info: Query analysis info
            data: Data structure to populate
        """
        markets = query_info.get('markets', [])
        if not markets:
            markets = ['win', 'top_5', 'top_10', 'top_20']  # Default markets
            
        tournament_names = list(data['tournaments'].keys())
        
        if not tournament_names:
            logger.warning("No tournaments for recommendations retrieval")
            return
        
        # Use a set to track unique recommendations by (player_id, market, sportsbook)
        unique_recs = set()
        recommendations = []
        
        # Get recommendations for each tournament and market
        for tournament_name in tournament_names:
            for market in markets:
                # Format market for SQL query
                db_market = market.replace(" ", "_").replace("-", "_").lower()
                
                # Get top value bets
                market_recs = self._get_value_bets(
                    conn, tournament_name, db_market, min_ev=5.0, limit=5
                )
                
                # Add to recommendations list with deduplication
                for rec in market_recs:
                    # Create a unique key for this recommendation
                    player_id = rec.get('player_id')
                    sportsbook = rec.get('sportsbook', '')
                    
                    rec_key = (player_id, db_market, sportsbook)
                    
                    # Check if we've already added this recommendation
                    if rec_key not in unique_recs:
                        unique_recs.add(rec_key)
                        
                        # Add market and tournament info
                        rec['market'] = db_market
                        rec['tournament'] = tournament_name
                        
                        # Add player display name
                        if player_id:
                            for player_name, player_info in data['players'].items():
                                if player_info.get('id') == player_id:
                                    rec['player_display_name'] = player_name
                                    break
                        
                        recommendations.append(rec)
        
        # Sort recommendations by adjusted EV
        recommendations.sort(key=lambda x: x.get('adjusted_ev', 0), reverse=True)
        
        # Limit to top 5 most valuable recommendations
        data['recommendations'] = recommendations[:5]
    
    def _format_player_name(self, name: str) -> str:
        """
        Format player name from database format (Last, First) to display format (First Last).
        
        Args:
            name: Player name in database format
            
        Returns:
            Formatted player name for display
        """
        if ',' in name:
            parts = name.split(',', 1)
            return f"{parts[1].strip()} {parts[0].strip()}"
        return name
    
    def _get_special_cases_mapping(self) -> Dict[str, str]:
        """
        Get mapping of special cases for player name matching.
        
        Returns:
            Dictionary mapping common variations to canonical names
        """
        return {
            "jt poston": "Poston, J.T.",
            "victor hovland": "Hovland, Viktor",
            "nicolai højgaard": "Hojgaard, Nicolai",
            "nikolai højgaard": "Hojgaard, Nicolai",
            "nikolai hojgaard": "Hojgaard, Nicolai",
            "rasmus højgaard": "Hojgaard, Rasmus",
            "ailano grillo": "Grillo, Emiliano",
            "ailano grio": "Grillo, Emiliano",
            "emiliano grio": "Grillo, Emiliano",
            "cristobal del solar": "Del Solar, Cristobal",
            "windham clark": "Clark, Wyndham",
            "men woo lee": "Lee, Min Woo",
            "menwoo lee": "Lee, Min Woo",
            "minwoo lee": "Lee, Min Woo",
            "minu lee": "Lee, Min Woo",
            "ludvig åberg": "Aberg, Ludvig",
            "ludvig oberg": "Aberg, Ludvig",
            "ludvig äberg": "Aberg, Ludvig",
            "stephen jaeger": "Jaeger, Stephan",
            "steven jaeger": "Jaeger, Stephan",
            "jj spaun": "Spaun, J.J.",
            "jj spawn": "Spaun, J.J.",
            "charlie hoffman": "Hoffman, Charley",
            "tom mckibben": "McKibbin, Tom",
            "roy mcilroy": "McIlroy, Rory",
            "john rahm": "Rahm, Jon",
            "john rom": "Rahm, Jon",
            "howton lee": "Li, Haotong", 
            "ricky fowler": "Fowler, Rickie",
            "thomas dietry": "Detry, Thomas",
            "adrien meronk": "Meronk, Adrian",
            "maverick mcneely": "McNealy, Maverick",
            "colin morikawa": "Morikawa, Collin",
            "patrick rogers": "Rodgers, Patrick",
            "windam clark": "Clark, Wyndham",
            "aldri potgater": "Potgieter, Aldrich",
            "justin su": "Suh, Justin",
            "ryan peak": "Peake, Ryan",
            "joe heith": "Highsmith, Joe",
            "callum hill": "Hill, Calum"
        }