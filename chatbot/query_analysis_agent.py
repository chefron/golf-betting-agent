"""
Query Analysis Agent for the Head Pro Chatbot

This module analyzes user queries to determine what specific data 
should be retrieved from our golf database to provide appropriate responses.
"""

import json
import re
import logging
import anthropic
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("head_pro.query_agent")

class QueryAnalysisAgent:
    def __init__(self, api_key: str):
        """
        Initialize the query analysis agent with the Anthropic API key.
        
        Args:
            api_key: The Anthropic API key for Claude
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-3-7-sonnet-20250219"  # Use the latest model
        
        # Common betting markets
        self.common_markets = [
            "win", "winner", "outright", 
            "top 5", "top five", "top-5",
            "top 10", "top ten", "top-10",
            "top 20", "top twenty", "top-20",
            "make cut", "miss cut", "mc", "first round leader", "frl"
        ]

    def analyze_query(self, user_message: str, conversation_history: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Analyze the user query to determine what data needs to be retrieved.
        
        Args:
            user_message: The user's message/query
            conversation_history: List of previous conversation turns
            
        Returns:
            Dictionary with query analysis information including required data types
        """
        # Do a quick pre-check for simple patterns
        query_info = self._pattern_based_analysis(user_message)
        if query_info:
            logger.info(f"Pattern-based analysis successful: {query_info}")
            return query_info
        
        # Format the conversation history for context
        context = self._format_conversation_history(conversation_history)
        
        # Create the prompt for Claude
        prompt = self._create_analysis_prompt(user_message, context)
        
        try:
            # Call Claude to analyze the query
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0.2,  # Low temperature for consistent outputs
                system="You are an expert golf analyst assistant that helps determine what data is needed to answer user queries.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract and parse the response
            response_text = response.content[0].text
            
            # Extract the JSON part of the response
            json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find JSON without the code block
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    logger.warning(f"Could not extract JSON from response: {response_text}")
                    return self._default_query_info()
            
            # Parse the JSON
            query_info = json.loads(json_str)
            logger.info(f"Query analysis complete: {query_info}")
            
            # Add metadata about the analysis
            query_info['analysis_timestamp'] = datetime.now().isoformat()
            query_info['analysis_method'] = 'claude'
            
            return query_info
            
        except Exception as e:
            logger.error(f"Error analyzing query: {e}")
            return self._default_query_info()
    
    def _pattern_based_analysis(self, user_message: str) -> Optional[Dict[str, Any]]:
        """
        Try to match common patterns in user queries without calling Claude.
        
        Args:
            user_message: The user's message/query
            
        Returns:
            Query info dictionary if a pattern was matched, None otherwise
        """
        # Lowercase the message for easier matching
        message = user_message.lower()
        
        # Detect betting-related terms and phrases
        betting_terms = ['bet', 'odds', 'value', 'worth', 'like', 'back', 'fade', 'chance', 
                        'wager', 'play', 'pick', 'punt', 'longshot', 'recommendation']
        
        # Check if message contains betting terms
        is_betting_related = any(term in message for term in betting_terms)
        
        # Common time qualifiers to strip from player name detection
        time_qualifiers = ['this week', 'today', 'tomorrow', 'this tournament', 
                        'this event', 'right now', 'currently']
        
        # Check for simple player mental form questions
        player_mental_form_pattern = r'(what|how).+(think|feel|opinion|thought).+about\s+([A-Za-z\s\.]+)(?:\?)?$'
        match = re.search(player_mental_form_pattern, message)
        if match:
            player_name_raw = match.group(3).strip()
            
            # Clean the player name by removing time qualifiers
            player_name = player_name_raw
            for qualifier in time_qualifiers:
                player_name = player_name.replace(qualifier, '').strip()
            
            # Only use the first 2 words max for player name (first and last)
            name_parts = player_name.split()
            if len(name_parts) > 2:
                player_name = ' '.join(name_parts[:2])
            
            return {
                'query_type': 'mental_form',
                'players': [player_name],
                'markets': ['win', 'top_5', 'top_10'] if is_betting_related else [],
                'needs_mental_form': True,
                'is_betting_related': is_betting_related,
                'analysis_method': 'pattern'
            }
        
        # Add a pattern specifically for betting-related player queries
        betting_player_pattern = r'(do you|should i|is|are|worth).+(like|back|fade|bet on|value)\s+([A-Za-z\s\.]+)(?:\?)?$'
        match = re.search(betting_player_pattern, message)
        if match:
            player_name_raw = match.group(3).strip()
            
            # Clean the player name
            player_name = player_name_raw
            for qualifier in time_qualifiers:
                player_name = player_name.replace(qualifier, '').strip()
            
            name_parts = player_name.split()
            if len(name_parts) > 2:
                player_name = ' '.join(name_parts[:2])
            
            return {
                'query_type': 'mental_form',
                'players': [player_name],
                'markets': ['win', 'top_5', 'top_10'],
                'needs_mental_form': True,
                'needs_player_personality': True,
                'is_betting_related': True,
                'analysis_method': 'pattern'
            }
        
        # Check for simple greeting/introduction
        if re.match(r'^(hi|hello|hey|what\'s up|sup|yo)\b', message) and len(message) < 20:
            return {
                'query_type': 'greeting',
                'players': [],
                'markets': [],
                'needs_mental_form': False,
                'is_betting_related': False,
                'analysis_method': 'pattern'
            }
            
        # Check for betting value questions
        betting_pattern = r'(who|which player|any).+(good|value|bet|play|recommendation|pick|like).+(this week|upcoming|tournament|event)'
        if re.search(betting_pattern, message):
            return {
                'query_type': 'betting_value',
                'players': [],  # We'll need to get all relevant players
                'markets': ['win', 'top_5', 'top_10'],  # Common markets
                'needs_mental_form': True,
                'is_betting_related': True,
                'analysis_method': 'pattern'
            }
        
        # No clear pattern match
        return None
    
    def _create_analysis_prompt(self, user_message: str, context: str) -> str:
        """
        Create the prompt for Claude to analyze the query.
        
        Args:
            user_message: The user's message
            context: Formatted conversation history
            
        Returns:
            Formatted prompt string
        """
        # Get current date for context
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # List common betting markets
        markets_str = ", ".join(self.common_markets)
        
        prompt = f"""
Please analyze this golf-related query to determine what specific database information we need to retrieve.

QUERY: "{user_message}"

DATE: {current_date}

PREVIOUS CONVERSATION CONTEXT:
{context}

Analyze the query and determine exactly what data we need to retrieve. Output a JSON object with these fields:

```json
{{
  "query_type": "<One of: player_info, mental_form, betting_value, general_chat>",
  "players": ["<List of player names mentioned or implied>"],
  "markets": ["<Any betting markets mentioned (win, top_5, etc.)>"],
  "needs_mental_form": <Boolean indicating if mental form analysis is needed>,
  "is_betting_related": <true/false>,
}}

GUIDELINES for each field:

"query_type":
    - mental_form: Queries specifically about a player's psychological state, confidence, or mental game
    - betting_value: Queries about betting recommendations, value plays, or who to bet on
    - player_info: General queries about players that don't fit the other categories
    - general_chat: Greetings, unrelated questions, or casual conversation

"players":
    - Include the names of specific players mentioned in the query
    - Fix mispellings and standardize common nicknames (e.g., "Scottie" → "Scottie Scheffler", "Rory" → "Rory McIlroy")
    - If no specific player is mentioned but the query is about players in general, leave as empty array []

"markets":
    - Include any specific betting markets mentioned in the query:
        - win (outright winner)
        - top_5 (top 5 finish)
        - top_10 (top 10 finish)
        - top_20 (top 20 finish)
        - make_cut
        - miss_cut
        - first_round_leader (FRL)
    - For betting queries without specific markets mentioned, default to the following: ["win", "top_5", "top_10", "top_20"]
    - For non-betting queries, leave as empty array []

"needs_mental_form":
    - true: For queries about players' psychological state, confidence, mental game, etc.
    - true: For betting-related queries (mental form affects betting recommendations)
    - false: For general chat or basic player info that doesn't require mental analysis

"is_betting_related":
    - true: For queries about odds, value, picks, recommendations, backing/fading players
    - true: For queries like "Do you like [player] this week?" (implicit betting question)
    - false: For queries like "What's [player]'s mental form?" (purely informational)

Please provide ONLY the JSON output, no other text.
"""
        return prompt
    
    def _format_conversation_history(self, conversation_history: List[Dict[str, Any]]) -> str:
        """
        Format conversation history for inclusion in the prompt.
        
        Args:
            conversation_history: List of previous conversation turns
            
        Returns:
            Formatted conversation history string
        """
        if not conversation_history:
            return "No previous conversation."
        
        formatted_history = []
        for i, turn in enumerate(conversation_history[-5:]):  # Only use last 5 turns
            role = turn.get('role', 'unknown')
            content = turn.get('content', '')
            
            if role.lower() == 'user':
                formatted_history.append(f"User: {content}")
            else:
                formatted_history.append(f"Head Pro: {content}")
        
        return "\n".join(formatted_history)
    
    def _default_query_info(self) -> Dict[str, Any]:
        """
        Return default query info when analysis fails.
        
        Returns:
            Default query info dictionary
        """
        return {
            'query_type': 'general_chat',
            'players': [],
            'tournaments': [],
            'time_period': 'current',
            'markets': [],
            'needs_mental_form': False,
            'needs_odds_data': False,
            'needs_player_personality': False,
            'analysis_method': 'default',
            'analysis_timestamp': datetime.now().isoformat()
        }


# Example usage
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    
    agent = QueryAnalysisAgent(api_key)
    
    # Test with some example queries
    test_queries = [
        "What do you think about Scottie Scheffler this week?",
        "Any good bets for The Masters?",
        "Is Jordan Spieth's mental game in shambles?",
        "Who has value in the top 10 market at the PGA Championship?",
        "Why did Bryson DeChambeau change his swing?",
        "Hey Head Pro, what's up?"
    ]
    
    for query in test_queries:
        print(f"\nAnalyzing query: {query}")
        result = agent.analyze_query(query)
        print(json.dumps(result, indent=2))