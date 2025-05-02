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
        
        # Common golf tournaments
        self.common_tournaments = [
            "Masters", "The Masters", "Augusta", 
            "PGA Championship", "The PGA", 
            "U.S. Open", "US Open", "The Open", "Open Championship", "British Open",
            "Players Championship", "The Players",
            "Tour Championship", "FedEx Cup", 
            "Waste Management", "Phoenix Open",
            "Travelers Championship", "Memorial Tournament",
            "Arnold Palmer Invitational", "API", 
            "Genesis Invitational", "Farmers Insurance Open",
            "Wells Fargo Championship", "Valspar Championship",
            "RBC Heritage", "Valero Texas Open"
        ]
        
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
        This is faster for simple queries.
        
        Args:
            user_message: The user's message
            
        Returns:
            Query info if a pattern was matched, None otherwise
        """
        # Lowercase the message for easier matching
        message = user_message.lower()
        
        # Check for simple greeting/introduction
        if re.match(r'^(hi|hello|hey|what\'s up|sup|yo)\b', message) and len(message) < 20:
            return {
                'query_type': 'greeting',
                'players': [],
                'tournaments': [],
                'time_period': 'current',
                'markets': [],
                'needs_mental_form': False,
                'needs_odds_data': False,
                'needs_general_golf_knowledge': True,
                'analysis_method': 'pattern'
            }
        
        # Check for simple player mental form questions
        player_mental_form_pattern = r'(what|how).+(think|feel|opinion|thought).+about\s+([A-Za-z\s\.]+)(?:\?)?$'
        match = re.search(player_mental_form_pattern, message)
        if match:
            player_name = match.group(3).strip()
            return {
                'query_type': 'player_mental_form',
                'players': [player_name],
                'tournaments': [],
                'time_period': 'current',
                'markets': [],
                'needs_mental_form': True,
                'needs_odds_data': False,
                'needs_general_golf_knowledge': True,
                'analysis_method': 'pattern'
            }
        
        # Check for betting value questions
        betting_pattern = r'(who|which player|any).+(good|value|bet|play|recommendation|pick|like).+(this week|upcoming|tournament|event)'
        if re.search(betting_pattern, message):
            return {
                'query_type': 'betting_value',
                'players': [],  # We'll need to get all relevant players
                'tournaments': ['current'],  # Assume current tournament
                'time_period': 'current',
                'markets': ['win', 'top_5', 'top_10'],  # Common markets
                'needs_mental_form': True,
                'needs_odds_data': True,
                'needs_general_golf_knowledge': True,
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
        
        # List common tournaments and golf events for reference
        tournaments_str = ", ".join(self.common_tournaments)
        markets_str = ", ".join(self.common_markets)
        
        prompt = f"""
I need your help analyzing this golf-related query to determine what specific database information we need to retrieve.

USER QUERY: "{user_message}"

PREVIOUS CONVERSATION CONTEXT:
{context}

CURRENT DATE: {current_date}

COMMON GOLF TOURNAMENTS: {tournaments_str}

COMMON BETTING MARKETS: {markets_str}

DATABASE TABLES AVAILABLE:
1. players - Contains player info (name, id, country, etc.)
2. mental_form - Contains player mental form scores and justifications
3. insights - Contains qualitative insights about players' mental state
4. odds - Contains current betting odds for various markets
5. bet_recommendations - Contains value betting opportunities based on odds and mental form

Analyze the query and determine exactly what data we need to retrieve. Output a JSON object with these fields:

```json
{{
  "query_type": "<One of: player_info, tournament_odds, mental_form, betting_value, general_chat>",
  "players": ["<List of player names mentioned or implied>"],
  "tournaments": ["<List of tournaments mentioned or implied>"],
  "time_period": "<Time period mentioned or implied (current, past, specific date)>",
  "markets": ["<Any betting markets mentioned (win, top_5, etc.)>"],
  "needs_mental_form": <Boolean indicating if mental form analysis is needed>,
  "needs_odds_data": <Boolean indicating if odds data is needed>,
  "needs_general_golf_knowledge": <Boolean indicating if general golf knowledge is required>,
  "specifics": "<Any additional specific information needed>"
}}
```

IMPORTANT GUIDELINES:
- If no specific player is mentioned but the query is about players in general, leave the "players" array empty
- If no specific tournament is mentioned but the query is about a tournament, add "current" to the tournaments array
- If multiple query types apply, choose the most specific one
- For time_period, use "current" if referring to present or upcoming events
- The "specifics" field should include any other important details needed to answer the query

Only provide the JSON output, no other text.
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
            'needs_general_golf_knowledge': True,
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