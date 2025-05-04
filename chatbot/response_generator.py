"""
Response Generator for the Head Pro Chatbot

This module generates responses in the Head Pro's distinctive voice based on
retrieved data and the original query.
"""

import logging
import json
import anthropic
from typing import Dict, List, Any, Optional
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("head_pro.response_generator")

class ResponseGenerator:
    def __init__(self, api_key: str, persona_file: str = "head_pro_persona.txt"):
        """
        Initialize the response generator.
        
        Args:
            api_key: Anthropic API key
            persona_file: Path to the file containing the Head Pro's persona
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-3-7-sonnet-20250219"  # Use the latest model
        
        # Load the Head Pro persona - fail if not available
        try:
            with open(persona_file, 'r', encoding='utf-8') as f:
                self.persona = f.read()
            logger.info(f"Loaded Head Pro persona from {persona_file}")
        except Exception as e:
            logger.error(f"Error loading persona file: {e}")
            raise ValueError(f"Failed to load Head Pro persona from {persona_file}")
    
    def generate_response(self, query: str, retrieved_data: Dict[str, Any], 
                         conversation_history: List[Dict[str, Any]] = None) -> str:
        """
        Generate the Head Pro's response based on retrieved data.
        
        Args:
            query: User's original query
            retrieved_data: Data retrieved from database
            conversation_history: Previous conversation messages
            
        Returns:
            Generated response text
        """
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
                temperature=0.7,  # Slightly higher temperature for more personality
                system=self.persona,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract the response
            generated_text = response.content[0].text
            
            return generated_text
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return self._generate_fallback_response(query, retrieved_data)
    
    def _format_data_as_context(self, data: Dict[str, Any]) -> str:
        """
        Format retrieved data as context for Claude with improved relevance focus.
        
        Args:
            data: Retrieved data structure
            
        Returns:
            Formatted context string
        """
        context_parts = []
        
        # Add query type
        query_type = data.get('query_info', {}).get('query_type', 'unknown')
        context_parts.append(f"QUERY TYPE: {query_type}")
        
        # Add tournament information
        if data.get('tournaments'):
            context_parts.append("\nTOURNAMENTS:")
            current_year = datetime.now().year  # Get current year
            for tournament_name, tournament_info in data['tournaments'].items():
                if tournament_info.get('not_found'):
                    context_parts.append(f"  {tournament_name}: Not found in database")
                else:
                    context_parts.append(f"  {tournament_name} ({current_year})")
        
        # For mental_form queries about specific players, only include that player
        if query_type == 'mental_form' and data.get('query_info', {}).get('players'):
            requested_players = data.get('query_info', {}).get('players', [])
            
            context_parts.append("\nPLAYER DATA:")
            for player_name, player_info in data.get('players', {}).items():
                # Check if this is the specific requested player
                is_requested = False
                for req_player in requested_players:
                    if req_player.lower() in player_name.lower() or player_name.lower() in req_player.lower():
                        is_requested = True
                        break
                
                if is_requested:
                    player_parts = [f"  {player_name}:"]
                    
                    # Indicate if player is in the tournament field
                    if player_info.get('in_field'):
                        player_parts.append("    [In tournament field]")
                    else:
                        player_parts.append("    [Not in tournament field]")
                    
                    # Add mental form if available
                    mental_form = player_info.get('mental_form', {})
                    if mental_form:
                        score = mental_form.get('score')
                        if score is not None:
                            player_parts.append(f"    Mental Form Score: {score}")
                        
                        justification = mental_form.get('justification')
                        if justification:
                            player_parts.append(f"    Mental Form Justification: {justification}")
                        
                        last_updated = mental_form.get('last_updated')
                        if last_updated:
                            player_parts.append(f"    Last Updated: {last_updated}")
                    
                    # Add personality info if available
                    if player_info.get('nicknames'):
                        player_parts.append(f"    Nicknames: {player_info.get('nicknames')}")
                    
                    if player_info.get('notes'):
                        player_parts.append(f"    Notes: {player_info.get('notes')}")
                    
                    # Add odds data if available
                    odds_data = data.get('odds', {}).get('by_player', {}).get(player_name, {})
                    if odds_data and player_info.get('in_field'):
                        player_parts.append("    Odds Data:")
                        
                        # Get the tournament
                        tournaments = list(data.get('tournaments', {}).keys())
                        tournament_name = tournaments[0] if tournaments else "Unknown Tournament"
                        
                        if tournament_name in odds_data:
                            for market, odds in odds_data[tournament_name].items():
                                market_display = market.replace('_', ' ').upper()
                                american_odds = odds.get('american_odds', 'N/A')
                                adjusted_ev = odds.get('adjusted_ev', 0)
                                player_parts.append(f"      {market_display}: {american_odds} (EV: {adjusted_ev:.1f}%)")
                    
                    context_parts.append("\n".join(player_parts))
        # For betting value queries or other types
        else:
            # For other query types, include relevant players
            if data.get('players'):
                context_parts.append("\nPLAYER DATA:")
                
                # Organize players by relevance
                requested_players = []
                recommended_players = []
                field_players = []
                
                for player_name, player_info in data.get('players', {}).items():
                    # Skip not found players
                    if player_info.get('not_found'):
                        context_parts.append(f"  {player_name}: Not found in database")
                        continue
                    
                    # Check if this is a requested player
                    is_requested = False
                    for req_player in data.get('query_info', {}).get('players', []):
                        if req_player.lower() in player_name.lower() or player_name.lower() in req_player.lower():
                            is_requested = True
                            break
                    
                    if is_requested:
                        requested_players.append((player_name, player_info))
                    elif player_info.get('is_recommendation', False):
                        recommended_players.append((player_name, player_info))
                    elif player_info.get('in_field', False):
                        field_players.append((player_name, player_info))
                
                # Format requested players first
                for player_name, player_info in requested_players:
                    player_parts = [f"  {player_name}:"]
                    
                    # Indicate if player is in the tournament field
                    if player_info.get('in_field'):
                        player_parts.append("    [In tournament field]")
                    else:
                        player_parts.append("    [Not in tournament field]")
                    
                    # Add mental form if available
                    mental_form = player_info.get('mental_form', {})
                    if mental_form:
                        score = mental_form.get('score')
                        if score is not None:
                            player_parts.append(f"    Mental Form Score: {score}")
                        
                        justification = mental_form.get('justification')
                        if justification:
                            player_parts.append(f"    Mental Form Justification: {justification}")
                        
                        last_updated = mental_form.get('last_updated')
                        if last_updated:
                            player_parts.append(f"    Last Updated: {last_updated}")
                    
                    # Add personality info if available
                    if player_info.get('nicknames'):
                        player_parts.append(f"    Nicknames: {player_info.get('nicknames')}")
                    
                    if player_info.get('notes'):
                        player_parts.append(f"    Notes: {player_info.get('notes')}")
                    
                    context_parts.append("\n".join(player_parts))
                
                # Then format recommended players for betting value queries
                if query_type == 'betting_value':
                    for player_name, player_info in recommended_players:
                        player_parts = [f"  {player_name}:"]
                        
                        # Indicate if player is in the tournament field
                        if player_info.get('in_field'):
                            player_parts.append("    [In tournament field]")
                        
                        # Add mental form if available
                        mental_form = player_info.get('mental_form', {})
                        if mental_form:
                            score = mental_form.get('score')
                            if score is not None:
                                player_parts.append(f"    Mental Form Score: {score}")
                            
                            justification = mental_form.get('justification')
                            if justification:
                                player_parts.append(f"    Mental Form Justification: {justification}")
                            
                            last_updated = mental_form.get('last_updated')
                            if last_updated:
                                player_parts.append(f"    Last Updated: {last_updated}")
                        
                        context_parts.append("\n".join(player_parts))
                    
                    # Add a few high-value players from the field
                    high_value_players = sorted(
                        field_players, 
                        key=lambda x: x[1].get('mental_form', {}).get('score', 0), 
                        reverse=True
                    )[:3]  # Top 3 by mental form score
                    
                    for player_name, player_info in high_value_players:
                        # Skip if already included in recommended
                        if player_name in [p[0] for p in recommended_players]:
                            continue
                            
                        player_parts = [f"  {player_name}:"]
                        
                        # Indicate player is in the tournament field
                        player_parts.append("    [In tournament field]")
                        
                        # Add mental form if available
                        mental_form = player_info.get('mental_form', {})
                        if mental_form:
                            score = mental_form.get('score')
                            if score is not None:
                                player_parts.append(f"    Mental Form Score: {score}")
                            
                            justification = mental_form.get('justification')
                            if justification:
                                player_parts.append(f"    Mental Form Justification: {justification}")
                        
                        context_parts.append("\n".join(player_parts))
        
        # Add betting recommendations for betting value queries
        if data.get('recommendations') and query_type == 'betting_value':
            context_parts.append("\nBETTING RECOMMENDATIONS:")
            for i, rec in enumerate(data['recommendations']):
                player_name = rec.get('player_display_name', 'Unknown Player')
                market = rec.get('market', '').replace('_', ' ').upper()
                tournament = rec.get('tournament', 'Unknown Tournament')
                odds = rec.get('american_odds', 'N/A')
                ev = rec.get('adjusted_ev', 0)
                sportsbook = rec.get('sportsbook', 'N/A')
                
                context_parts.append(f"  {i+1}. {player_name} - {market} at {tournament}")
                context_parts.append(f"     Odds: {odds} ({sportsbook}), Adjusted EV: {ev:.1f}%")
                
                # Add mental form context for this recommendation
                mental_score = rec.get('mental_score')
                if mental_score is not None:
                    context_parts.append(f"     Mental Form Score: {mental_score}")
        
        return "\n".join(context_parts)
    
    def _format_player_context(self, player_name: str, player_info: Dict[str, Any]) -> str:
        """
        Format player information for context in a consistent way.
        
        Args:
            player_name: Display name of the player
            player_info: Dictionary of player information
            
        Returns:
            Formatted player information string
        """
        player_parts = [f"  {player_name}:"]
        
        # Indicate if player is in the field
        if player_info.get('in_field'):
            player_parts.append("    [In tournament field]")
        
        # Add mental form if available
        mental_form = player_info.get('mental_form', {})
        if mental_form:
            score = mental_form.get('score')
            if score is not None:
                player_parts.append(f"    Mental Form Score: {score}")
            
            justification = mental_form.get('justification')
            if justification:
                player_parts.append(f"    Mental Form Justification: {justification}")
            
            last_updated = mental_form.get('last_updated')
            if last_updated:
                player_parts.append(f"    Last Updated: {last_updated}")
        
        # Add personality info if available
        if player_info.get('nicknames'):
            player_parts.append(f"    Nicknames: {player_info.get('nicknames')}")
        
        if player_info.get('notes'):
            player_parts.append(f"    Notes: {player_info.get('notes')}")
        
        # Return the formatted player context
        return "\n".join(player_parts)
    
    def _format_conversation_history(self, history: List[Dict[str, Any]] = None) -> str:
        """
        Format conversation history for inclusion in the prompt.
        
        Args:
            history: List of conversation messages
            
        Returns:
            Formatted conversation history string
        """
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
        """
        Create the prompt for generating a response.
        
        Args:
            query: User's original query
            context: Formatted context from retrieved data
            conv_history: Formatted conversation history
            
        Returns:
            Prompt string
        """
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        prompt = f"""

<CURRENT TASK>
You're currently chatting with a user on the Head Pro website. The date is {current_date}. Please respond directly to the following query:

<QUERY>
{query}
<QUERY>

<CONTEXT>

<CONVERSATION>
Here's the rest of your conversation up to this point:
{conv_history}
</CONVERSATION>

<DATA>
Here's relevant data retrieved from your database:
{context}
</DATA>

</CONTEXT>

<INSTRUCTIONS>
1. Keep your response relatively concise and focused directly on answering the query. Remeber your voice: blunt, confident, dryly witty.
2. When discussing players' mental form, use the scores (-1 to +1) and justifications provided, but add your own colorful elaboration.
3. For betting recommendations, focus on the psychological angle that statistical models can't quantify. Don't just list the odds and EV numbers - explain WHY you believe there's value based on your read of the player's mental state.
4. If the query is about a future tournament, explain that your model doesn't work for future events because players' mental form changes constantly, but you can give a general read on players' current form. Remeber, today is {current_date}. You have an unfortunate tendency to hallucinate information about future tournaments, and you need to avoid doing that at all costs. Just stick to the provided data, please.
5. Most important, DON'T MAKE SHIT UP. I can't reiterate this enough.
</INSTRUCTIONS>

Now please respond to the user as THE HEAD PRO, giving your unfiltered take directly addressing their query.
</CURRENT TASK>
"""
        # Print the full prompt to console for debugging
        print("\n" + "="*80)
        print("FULL PROMPT BEING SENT TO CLAUDE:")
        print("="*80)
        print(prompt)
        print("="*80 + "\n")
        
        return prompt
    
    def _generate_fallback_response(self, query: str, data: Dict[str, Any]) -> str:
        """
        Generate a fallback response when the main response generation fails.
        
        Args:
            query: User's original query
            data: Retrieved data structure
            
        Returns:
            Fallback response string
        """
        query_type = data.get('query_info', {}).get('query_type', 'unknown')
        
        fallbacks = {
            'greeting': "Well hello there. What can The Head Pro help you with today? Looking for betting value, mental form insights, or just a straight-shooting take on what's happening in the golf world?",
            
            'mental_form': "Listen, I'd love to give you a proper read on this player's mental game, but I'm having trouble accessing my notes at the moment. Ask me about someone else, or be more specific about what you want to know.",
            
            'betting_value': "I've got some thoughts on betting value, but my numbers aren't loading properly right now. Try asking me about a specific player's mental form instead, or come back in a bit when my system's cooperating.",
            
            'player_info': "Can't pull up my full dossier on this player at the moment. My system's on the fritz. Try asking something more specific about their mental form - that part of my brain is still working.",
            
            'general_chat': "Listen, my mental database is a bit foggy at the moment. The 19th hole might've been a few too many last night. What else can I help you with?"
        }
        
        return fallbacks.get(query_type, 
            "Something's gone sideways with my system. The tech boys tell me it'll be sorted soon. In the meantime, try asking me something specific about a player's mental state or maybe some betting recommendations for the upcoming tournament."
        )