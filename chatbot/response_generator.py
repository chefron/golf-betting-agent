import logging
import anthropic
from typing import Dict, List, Any
from datetime import datetime

logger = logging.getLogger("head_pro.response_generator")

class ResponseGenerator:
    def __init__(self, api_key: str, persona_file: str = "head_pro_persona.txt"):
        """Initialize the response generator."""
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-3-7-sonnet-20250219"
        
        # Load the Head Pro persona
        try:
            with open(persona_file, 'r', encoding='utf-8') as f:
                self.persona = f.read()
            logger.info(f"Loaded Head Pro persona from {persona_file}")
        except Exception as e:
            logger.error(f"Error loading persona file: {e}")
            raise ValueError(f"Failed to load Head Pro persona from {persona_file}")
    
    def generate_response(self, query: str, retrieved_data: Dict[str, Any], 
                         conversation_history: List[Dict[str, Any]] = None) -> str:
        """Generate the Head Pro's response based on retrieved data."""
        logger.info(f"Generating response for query: {query}")
        
        # Format the retrieved data as context
        context = self._format_data_as_context(retrieved_data)
        
        # Format conversation history
        conv_history = self._format_conversation_history(conversation_history)
        
        # Create the prompt
        prompt = self._create_prompt(query, context, conv_history)
        
        try:
            # Call Claude to generate response
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                temperature=0.7,
                system=self.persona,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract the response
            return response.content[0].text
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return self._generate_fallback_response(query, retrieved_data)
    
    def _format_data_as_context(self, data: Dict[str, Any]) -> str:
        """Format retrieved data as context for Claude."""
        context_parts = []
        
        # Add query type
        query_type = data.get('query_info', {}).get('query_type', 'unknown')
        context_parts.append(f"QUERY TYPE: {query_type}")
        
        # Add current tournament
        tournament_name = data.get('tournament', {}).get('name', 'Unknown Tournament')
        context_parts.append(f"\nCURRENT TOURNAMENT: {tournament_name}")
        
        # Add player data if present
        if data.get('players'):
            context_parts.append("\nPLAYER DATA:")
            for player_name, player_info in data['players'].items():
                if player_info.get('not_found'):
                    context_parts.append(f"  {player_name}: Not found in database")
                    continue
                
                player_parts = [f"  {player_name}:"]
                
                # Add in-field status
                if player_info.get('in_field'):
                    player_parts.append("    In the field this week: Yes")
                else:
                    player_parts.append("    In the field this week: No")
                
                # Add mental form
                mental_form = player_info.get('mental_form')
                if mental_form:
                    player_parts.append(f"    Mental Form Score: {mental_form.get('score')}")
                    player_parts.append(f"    Mental Form Justification: {mental_form.get('justification')}")
                    player_parts.append(f"    Last Updated: {mental_form.get('last_updated')}")
                
                # Add personality data
                if player_info.get('nicknames'):
                    player_parts.append(f"    Nicknames: {player_info['nicknames']}")
                if player_info.get('notes'):
                    player_parts.append(f"    Notes: {player_info['notes']}")
                
                # Add odds data
                odds = player_info.get('odds')
                if odds and player_info.get('in_field'):
                    player_parts.append("    Odds Data:")
                    for market, market_data in odds.items():
                        player_parts.append(f"      {market.upper()}: {market_data.get('american_odds')} " +
                                          f"(EV: {market_data.get('adjusted_ev', 0):.1f}%)")
                
                context_parts.append("\n".join(player_parts))
        
        # Add betting recommendations
        if data.get('betting_recommendations'):
            context_parts.append("\nBETTING RECOMMENDATIONS:")
            for i, rec in enumerate(data['betting_recommendations']):
                context_parts.append(f"  {i+1}. {rec['player_name']} - {rec['market'].replace('_', ' ').upper()}")
                context_parts.append(f"     Odds: {rec['american_odds']} ({rec['sportsbook']})")
                context_parts.append(f"     Adjusted EV: {rec['adjusted_ev']:.1f}%")
                context_parts.append(f"     Mental Score: {rec['mental_score']}")
                context_parts.append(f"     Mental Justification: {rec['mental_justification']}")
        
        # Add mental rankings
        if data.get('mental_rankings', {}).get('highest'):
            context_parts.append("\nMENTALLY STRONGEST PLAYERS:")
            for i, player in enumerate(data['mental_rankings']['highest']):
                context_parts.append(f"  {i+1}. {player['player_name']}")
                context_parts.append(f"     Mental Score: {player['mental_score']}")
                context_parts.append(f"     Mental Justification: {player['mental_justification']}")
        
        if data.get('mental_rankings', {}).get('lowest'):
            context_parts.append("\nMENTALLY WEAKEST PLAYERS:")
            for i, player in enumerate(data['mental_rankings']['lowest']):
                context_parts.append(f"  {i+1}. {player['player_name']}")
                context_parts.append(f"     Mental Score: {player['mental_score']}")
                context_parts.append(f"     Mental Justification: {player['mental_justification']}")
        
        # Add tournament field data
        if data.get('tournament_field'):
            context_parts.append(f"\nPLAYERS IN {tournament_name} FIELD:")
            for i, player in enumerate(data['tournament_field']):
                context_parts.append(f"  {i+1}. {player['player_name']}")
                context_parts.append(f"     Mental Score: {player['mental_score']}")
                context_parts.append(f"     Mental Justification: {player['mental_justification']}")
        
        return "\n".join(context_parts)
    
    def _format_conversation_history(self, history: List[Dict[str, Any]] = None) -> str:
        """Format conversation history for inclusion in the prompt."""
        if not history:
            return "No previous conversation."
        
        # Only include the last few messages to keep the context manageable
        recent_history = history[-5:] if len(history) > 5 else history
        
        history_parts = []
        for msg in recent_history:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            
            if role.lower() == 'user':
                history_parts.append(f"User: {content}")
            else:
                history_parts.append(f"Head Pro: {content}")
        
        return "\n".join(history_parts)
    
    def _create_prompt(self, query: str, context: str, conv_history: str) -> str:
        """Create the prompt for generating a response."""
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        prompt = f"""
<CURRENT TASK>
You're currently chatting with a user on the Head Pro website. The date is {current_date}. Please respond directly to the following query:

<QUERY>
{query}
</QUERY>

<CONTEXT>
<CONVERSATION>
Here's the recent conversation:
{conv_history}
</CONVERSATION>

<DATA>
Here's relevant data retrieved from your database:
{context}
</DATA>
</CONTEXT>

<INSTRUCTIONS>
1. Keep your response relatively concise, focused on answering the query with your blunt, confident, dryly witty tone.
2. When discussing players' mental form, use the scores (-1 to +1) and justifications provided, but add your own colorful elaboration. If the scores aren't provided, it's possible something is broken and you should tell the user that you don't have access to your notes at the moment.
3. For betting recommendations, focus on the psychological angle that statistical models can't quantify.
4. If the query is about a future tournament, explain that you don't have data for future events.
5. Today is {current_date}. It's 2025, not 2024. For some reason you always get confused about this.
6. Most importantly, DON'T MAKE SHIT UP. I can't reiterate this enough. Only analyze players where mental form data is provided. It's better to say "I don't have data on that" rather than filling gaps with your own assumptions.
</INSTRUCTIONS>

Now please respond to the user as THE HEAD PRO, giving your unfiltered take directly addressing their query.
</CURRENT TASK>
"""
        # Print full prompt for debugging
        print("\n" + "="*80)
        print("FULL PROMPT BEING SENT TO CLAUDE:")
        print("="*80)
        print(prompt)
        print("="*80 + "\n")
        
        return prompt
    
    def _generate_fallback_response(self, query: str, data: Dict[str, Any]) -> str:
        """Generate a fallback response when the main response generation fails."""
        query_type = data.get('query_info', {}).get('query_type', 'unknown')
        
        fallbacks = {
            'greeting': "Well hello there. What can The Head Pro help you with today? Looking for betting value, mental form insights, or just a straight-shooting take on what's happening in the golf world?",
            
            'player_info': "Listen, I've got a cabinet full of mental form files, but I can't seem to locate that particular player's folder at the moment. My filing system's been compromised by a few too many scotches. Try asking about someone else, or be more specific about what you want to know.",
            
            'betting_current': "I've got some thoughts on betting value, but my numbers aren't loading properly right now. Try asking me about a specific player's mental form instead, or come back in a bit when my system's cooperating.",
            
            'betting_other': "I only track mental form and betting value for the current tournament. I can't tell you about future events because players' mental states are constantly in flux. Ask me about the current tournament instead.",
            
            'mental_rankings': "The mental leaderboard is undergoing maintenance at the moment. The intern spilled bourbon on my psychological evaluation files. Try asking about a specific player or betting recommendations instead.",
            
            'tournament_field': "I could tell you who's playing this week, but my tournament roster seems to have gone missing. Probably left it at the 19th hole last night. Ask me something specific about a player you're interested in."
        }
        
        return fallbacks.get(query_type, 
            "Listen, my mental database is a bit foggy at the moment. The 19th hole might've been a few too many last night. What else can I help you with?"
        )