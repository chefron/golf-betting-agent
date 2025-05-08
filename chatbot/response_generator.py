import logging
import anthropic
import json
from typing import Dict, List, Any
from datetime import datetime

logger = logging.getLogger("head_pro.response_generator")

class ResponseGenerator:
    def __init__(self, api_key: str, persona_file: str = "head_pro_persona.txt", faqs_file: str = "head_pro_faqs.json"):
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
        
        # Load FAQs
        try:
            with open(faqs_file, 'r', encoding='utf-8') as f:
                self.faqs = json.load(f)
            logger.info(f"Loaded {len(self.faqs)} FAQs from {faqs_file}")
        except Exception as e:
            logger.error(f"Error loading FAQs file: {e}")
    
    def generate_response(self, query: str, retrieved_data: Dict[str, Any], 
                         conversation_history: List[Dict[str, Any]] = None) -> str:
        """Generate the Head Pro's response based on retrieved data."""
        logger.info(f"Generating response for query: {query}")

        # Get query type directly from retrieved_data
        query_type = retrieved_data.get('query_info', {}).get('query_type', 'unknown')
        
        # Format the retrieved data as context
        context = self._format_data_as_context(retrieved_data)
        
        # Format conversation history
        conv_history = self._format_conversation_history(conversation_history)
        
        # Create the prompt
        prompt = self._create_prompt(query, context, conv_history, query_type)
        
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
                # Add blank line before each player for readability
                context_parts.append("")

                if player_info.get('not_found'):
                    context_parts.append(f"  {player_name}: Not found in database")
                    continue
                
                player_parts = [f"  {player_name}:"]
                
                # Add in-field status
                if player_info.get('in_field'):
                    player_parts.append("    In the field this week: Yes")
                else:
                    player_parts.append("    In the field this week: No")

                # Add odds data
                odds = player_info.get('odds')
                if odds and player_info.get('in_field'):
                    player_parts.append("    Odds Data:")
                    for market, market_data in odds.items():
                        # Format market name properly
                        market_display = market.replace('_', ' ').title() if '_' in market else market.capitalize()
                        
                        # Add sportsbook(s) to odds display (change #4)
                        sportsbook = market_data.get('sportsbook', '')
                        sportsbook_display = f" ({sportsbook})" if sportsbook else ""

                        player_parts.append(f"      {market_display}: {market_data.get('american_odds')}{sportsbook_display}, " +
                                        f"EV: {market_data.get('adjusted_ev', 0):.1f}%")
                
                # Add mental form
                mental_form = player_info.get('mental_form')
                if mental_form:
                    player_parts.append(f"    Mental Form Score: {mental_form.get('score')}")
                    player_parts.append(f"    Mental Form Justification: {mental_form.get('justification')}")
                    # Show last updated date (remove time for readability)
                    last_updated = mental_form.get('last_updated', '')
                    if last_updated and ' ' in last_updated:
                        last_updated = last_updated.split(' ')[0]
                    player_parts.append(f"    Last Updated: {last_updated}")

                # Add recent tournament Results
                recent_tournaments = player_info.get('recent_tournaments')
                if recent_tournaments:
                    player_parts.append("    Recent Tournament Results:")
                    for tournament in recent_tournaments:
                        event_name = tournament.get('event_name', 'Unknown')
                        tour = tournament.get('tour', '').upper()
                        finish = tournament.get('finish_position', '')
                        date = tournament.get('event_date', '')
                        # Format the date to just show year-month-day
                        if date and ' ' in date:
                            date = date.split(' ')[0]
                        
                        player_parts.append(f"      • {date} | {tour} | {event_name}: {finish}")
                
                # Add personality data
                if player_info.get('nicknames'):
                    player_parts.append(f"    Nicknames: {player_info['nicknames']}")
                if player_info.get('notes'):
                    player_parts.append(f"    Notes: {player_info['notes']}")
                
                context_parts.append("\n".join(player_parts))
        
        # Add betting recommendations - MODIFIED TO GROUP BY PLAYER
        if data.get('betting_recommendations'):
            context_parts.append("\nBETTING RECOMMENDATIONS (organized by player):")
            
            # First, group recommendations by player
            players_recommendations = {}
            for rec in data['betting_recommendations']:
                player_name = rec['player_name']
                if player_name not in players_recommendations:
                    players_recommendations[player_name] = {
                        'mental_score': rec['mental_score'],
                        'mental_justification': rec['mental_justification'],
                        'bets': []
                    }
                
                players_recommendations[player_name]['bets'].append({
                    'market': rec['market'],
                    'american_odds': rec['american_odds'],
                    'decimal_odds': rec['decimal_odds'],
                    'sportsbook': rec['sportsbook'],
                    'adjusted_ev': rec['adjusted_ev']
                })
            
            # Now output the organized recommendations
            for i, (player_name, player_data) in enumerate(players_recommendations.items(), 1):
                context_parts.append(f"  {i}. {player_name} (Mental Score: {player_data['mental_score']})")
                
                # Group similar bets (same market and odds)
                market_groups = {}
                for bet in player_data['bets']:
                    key = f"{bet['market']}:{bet['american_odds']}"
                    if key not in market_groups:
                        market_groups[key] = {
                            'market': bet['market'],
                            'american_odds': bet['american_odds'],
                            'adjusted_ev': bet['adjusted_ev'],
                            'sportsbooks': []
                        }
                    market_groups[key]['sportsbooks'].append(bet['sportsbook'])
                
                # Output each bet type
                for group in market_groups.values():
                    sportsbooks_str = ", ".join(group['sportsbooks'])
                    context_parts.append(f"     - {group['market'].upper()}: {group['american_odds']} ({sportsbooks_str}), EV: {group['adjusted_ev']:.1f}%")
                
                # Add mental assessment
                context_parts.append(f"     Mental Assessment: {player_data['mental_justification']}")
                
                # Add blank line between players for readability
                if i < len(players_recommendations):
                    context_parts.append("")
        
        # Add mental rankings
        if data.get('mental_rankings', {}).get('highest'):
            context_parts.append(f"\nMENTALLY STRONGEST PLAYERS from all tours (please note that only some are playing in the {tournament_name}):")
            for i, player in enumerate(data['mental_rankings']['highest']):
                context_parts.append(f"  {i+1}. {player['player_name']}")
                context_parts.append(f"     In the field this week: {'Yes' if player.get('in_field') else 'No'}")
                context_parts.append(f"     Mental Score: {player['mental_score']}")
                context_parts.append(f"     Mental Justification: {player['mental_justification']}")
        
        if data.get('mental_rankings', {}).get('lowest'):
            context_parts.append(f"\nMENTALLY WEAKEST PLAYERS from all tours (please note that only some are playing in the {tournament_name}):")
            for i, player in enumerate(data['mental_rankings']['lowest']):
                context_parts.append(f"  {i+1}. {player['player_name']}")
                context_parts.append(f"     In the field this week: {'Yes' if player.get('in_field') else 'No'}")
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
        
        # Only include the last ten messages to keep the context manageable
        recent_history = history[-10:] if len(history) > 10 else history
        
        history_parts = []
        for msg in recent_history:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            
            if role.lower() == 'user':
                history_parts.append(f"User: {content}")
            else:
                history_parts.append(f"Head Pro: {content}")
        
        return "\n".join(history_parts)
    
    def _create_prompt(self, query: str, context: str, conv_history: str, query_type: str) -> str:
        """Create the prompt for generating a response."""
        current_date = datetime.now().strftime("%Y-%m-%d")

        # Create FAQs section only for 'other_question' queries
        faqs_section = ""
        if query_type == 'other_question':
            faqs_section = "\n<FAQS>\n"
            for faq in self.faqs:
                faqs_section += f"Q: {faq['question']}\n"
                faqs_section += f"A: {faq['answer']}\n\n"
            faqs_section += "</FAQS>\n"
        
        prompt = f"""
<CURRENT TASK>
You're currently chatting with a user on the Head Pro website. The date is {current_date}. Please respond directly to the following query:

<QUERY>
{query}
</QUERY>

<CONTEXT>
<CONVERSATION>
Here's your conversation with them up to this point:
{conv_history}
</CONVERSATION>

<DATA>
Here's some potentially relevant data retrieved from your database:
{context}
</DATA>
{faqs_section}
</CONTEXT>

<INSTRUCTIONS>
1. Keep your response relatively concise, focused on answering the query with your blunt, confident, dryly witty tone.
2. When discussing players' mental form, use the scores (-1 to +1) and justifications provided, but add your own colorful elaboration. If the scores aren't provided, it's possible something is broken and you should tell the user that you don't have access to your notes at the moment. Never fabricate data!
3. For betting recommendations, focus on the psychological angle that statistical models can't quantify. Only recommened bets where the player has a mental score over .2 AND the EV is positive (preferable over +6.0%)! Many players with positive mental scores are still EV-negative because the odds aren't favorable enough.
4. If the query is about a future tournament, explain that you don't have data for future events.
5. For general questions an, see if any of the FAQs apply and use that information in your response, but maintain your distinctive voice.
6. Today is {current_date}. It's 2025, not 2024. For some reason you tend to get confused about this when referring to past and future years. 2024 was last year, 2025 is this year, 2026 is next year.
7. Most importantly, DON'T MAKE SHIT UP. I can't reiterate this enough. Only analyze players where mental form data is provided. It's better to say "I don't have data on that" rather than filling gaps with your own assumptions.
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