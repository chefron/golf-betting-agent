import logging
import re
import json
import anthropic
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger("head_pro.query_agent")

class QueryAnalysisAgent:
    def __init__(self, api_key: str, current_tournament: str = "Unknown Tournament"):
        """Initialize the query analysis agent with the Anthropic API key."""
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-3-7-sonnet-20250219"
        self.current_tournament = current_tournament

    def _pattern_based_analysis(self, user_message: str) -> Optional[Dict[str, Any]]:
        """Perform simple pattern-based analysis for common query types."""
        # Convert message to lowercase for easier matching
        message_lower = user_message.lower().strip()
        
        # More flexible greeting pattern with common variations and allowing words after
        greeting_patterns = [
            # Basic greetings with possible letter repetitions, allowing words after
            r'^h+[aeiy]+l*l+o+(\s+.*)?$',      # hello, hellooo + optional words after
            r'^h+[eiy]+y+(\s+.*)?$',           # hey, heyyy + optional words after
            r'^y+o+(\s+.*)?$',                 # yo, yooo + optional words after
            r'^s+u+p+(\s+.*)?$',               # sup, suuup + optional words after
            r'^howdy(\s+.*)?$',
            r'^greetings(\s+.*)?$',
            r'^hiya(\s+.*)?$',
            r'^what\'?s\s+up(\s+.*)?$',        # what's up, whats up + optional words after
            
            # Time-based greetings
            r'^good\s+morning(\s+.*)?$',
            r'^good\s+afternoon(\s+.*)?$',
            r'^good\s+evening(\s+.*)?$',
            r'^good\s+day(\s+.*)?$',
            r'^morning(\s+.*)?$',
            r'^afternoon(\s+.*)?$',
            r'^evening(\s+.*)?$'
        ]
        
        # Check if any greeting pattern matches
        for pattern in greeting_patterns:
            if re.match(pattern, message_lower) and len(message_lower) < 25:
                logger.info(f"Pattern match: simple greeting detected with pattern: {pattern}")
                query_info = {
                    'query_type': 'greeting',
                    'players': [],
                    'analysis_timestamp': datetime.now().isoformat()
                }
                return self._populate_needs_fields(query_info)
        
        # No pattern match found, return None
        return None
        
    def analyze_query(self, user_message: str, conversation_history: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Analyze the user query to determine what data needs to be retrieved."""

        # Do a quick pre-check for simple patterns
        query_info = self._pattern_based_analysis(user_message)
        if query_info:
            logger.info(f"Pattern-based analysis successful: {query_info}")
            return query_info
        
        # Format conversation history for context
        context = self._format_conversation_history(conversation_history)
        
        # Create the prompt for Claude
        prompt = self._create_analysis_prompt(user_message, context)
        
        try:
            # Call Claude to analyze the query
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                temperature=0.2,
                system="You analyze golf-related queries to determine what database information is needed.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract and parse the response
            response_text = response.content[0].text

            # Add this print statement for testing
            print("\n" + "="*80)
            print("FULL QUERY ANALYSIS RESPONSE FROM LLM:")
            print("="*80)
            print(response_text)
            print("="*80 + "\n")
            
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

            # Add needs_* fields based on query_type
            query_info = self._populate_needs_fields(query_info)

            logger.info(f"Query analysis complete: {query_info}")
            
            # Add metadata about the analysis
            query_info['analysis_timestamp'] = datetime.now().isoformat()
            
            return query_info
            
        except Exception as e:
            logger.error(f"Error analyzing query: {e}")
            return self._default_query_info()
    
    def _create_analysis_prompt(self, user_message: str, context: str) -> str:
        """Create the simplified prompt for Claude to analyze the query."""
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        prompt = f"""
Analyze this golf-related query to determine exactly what database information we need to retrieve.

QUERY: "{user_message}"

DATE: {current_date}
CURRENT TOURNAMENT: {self.current_tournament}

PREVIOUS CONVERSATION CONTEXT:
{context}

Follow this EXACT decision tree - stop at the FIRST YES answer and output the corresponding JSON:

1. Does the query mention specific players?
   - If YES: Set query_type="player_info" and include the player names in the players list (fix misspellings and standardize common nicknames like "Rory" → "Rory McIlroy"). STOP HERE AND OUTPUT JSON.
   - If NO: Continue to step 2.

2. Is the query about DFS (Daily Fantasy Sports) recommendations for the {self.current_tournament}?
   - If YES: Set query_type="dfs_current" and players=[] (empty list). STOP HERE AND OUTPUT JSON.
   - If NO: Continue to step 3.

3. Is the query about betting recommendations (non-DFS-related) for the {self.current_tournament}? This includes explicit betting queries (outrights, finish positions, matchups, 3-ball, FRL, etc.) as well as questions like "Who should I bet on this week?" or "Give me your best {self.current_tournament} plays."
   - If YES: Set query_type="betting_current" and players=[] (empty list). STOP HERE AND OUTPUT JSON.
   - If NO: Continue to step 4.

4. Is the query about betting or DFS recommendations for a tournament OTHER than the {self.current_tournament} (such as a future major, a LIV Golf event, a DP World Tour Event, or a different PGA event)?
   - If YES: Set query_type="betting_other" and players=[]. STOP HERE AND OUTPUT JSON.
   - If NO: Continue to step 5.

5. Is the query about the {self.current_tournament} field from a non-betting perspective? For example, "Who do you like this week? or "Who looks strongest/weakest for the {self.current_tournament}?" (mental assessment of the field without explicit betting intent).
   - If YES: Set query_type="tournament_field" and players=[]. STOP HERE AND OUTPUT JSON.
   - If NO: Continue to step 6.

6. Is the query about mental rankings or the mental states of players in general (not specific to {self.current_tournament})? This includes questions about who are the mentally strongest/weakest players overall, who are our favorite and least favorite players, and who we like or not like in general.
   - If YES: Set query_type="mental_rankings" and players=[]. STOP HERE AND OUTPUT JSON.
   - If NO: Continue to step 7.

7. Is the query a simple greeting or introduction? This includes any brief conversational opener that doesn't ask for specific information.
   - If YES: Set query_type="greeting" and players=[]. STOP HERE AND OUTPUT JSON.
   - If NO: Set query_type="other_question" and players=[]. OUTPUT JSON.

Output JSON with EXACTLY these fields:
```json
{{
  "query_type": "<player_info|dfs_current|betting_current|betting_other|mental_rankings|tournament_field|greeting|other_question>",
  "players": ["<List of specific player names mentioned>"]
}}

CRITICAL: Follow the decision tree in exact order. Stop at the FIRST YES answer and output the corresponding JSON.
"""
        return prompt

    def _populate_needs_fields(self, query_info):
        """Populate needs_* fields based on query_type"""
        # Initialize all needs fields to False
        query_info['needs_player_data'] = False
        query_info['needs_betting_recommendations'] = False
        query_info['needs_dfs_recommendations'] = False
        query_info['needs_mental_rankings'] = False
        query_info['needs_tournament_field'] = False
        
        # Set appropriate field based on query_type
        query_type = query_info.get('query_type', 'other_question')
        
        if query_type == 'player_info':
            query_info['needs_player_data'] = True
        elif query_type == 'dfs_current':
            query_info['needs_dfs_recommendations'] = True
        elif query_type == 'betting_current':
            query_info['needs_betting_recommendations'] = True
        elif query_type == 'mental_rankings':
            query_info['needs_mental_rankings'] = True
        elif query_type == 'tournament_field':
            query_info['needs_tournament_field'] = True
        
        # Other query types (greeting, betting_other, other_question) don't need any specific data
        
        return query_info
    
    def _format_conversation_history(self, conversation_history: List[Dict[str, Any]]) -> str:
        """Format conversation history for inclusion in the prompt."""
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
        """Return default query info when analysis fails."""
        query_info = {
            'query_type': 'other_question',
            'players': [],
            'analysis_timestamp': datetime.now().isoformat()
        }
        return self._populate_needs_fields(query_info)