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
        
        # Define complete instruction sets for each query type
        self.instruction_templates = {
            'greeting': """

1. This is a simple greeting. Briefly welcome the user in your characteristic style: blunt, confident, dryly witty. Keep it short and natural. Less is more.
2. Don't fabricate any data or golf facts. In fact, please don't mention any players at all.
3. Today's date is {current_date}. Please don't get confused about the current year when referring to past and future years. 2024 was last year, 2025 is this year, 2026 is next year.""",
            
            'player_info': """
            
1. When discussing a players' mental form, use the scores (-1 to +1) and justifications provided below, but add your own colorful elaboration. That said, don't make up facts or statistics. Just stick to the provided data, please.
2. Only recommend bets when the player has a mental score over +0.25 AND the EV is positive (over +6.0% for placement bets and 10% for winners). Many players with positive mental scores are still EV-negative because the odds aren't favorable enough. Also, please exercise caution in recommending longshit winners, which are typically only worth a sprinkle.
3. We only have odds data for the {tournament_name}. If the user is asking about a future tournament, please tell them you don't have data for it yet because mental states change week-to-week. If they're asking about an event from a different tour (LIV, DP World, Korn Ferry, LPGA, etc.), please tell them that your model only covers PGA events (though you DO keep mental scores for some non-PGA players, which you're welcome to share).
4. Please refrain from mentioning players whose names don't appear in the below context. When referring to players whose names DO appear in the context, please use their full name the first time you mention them unless it's obvious who you're referring to. Remember, the user doesn't have access to the context we provide you, so clarity is paramount!
5. Today's date is {current_date}. Please don't get confused about the current year when referring to past and future years. 2024 was last year, 2025 is this year, 2026 is next year.
6. Last and most importantly, NEVER FABRICATE DATA. If the query asks for data that isn't provided below, it's better to say "I don't have data on that" rather than filling gaps with your own assumptions. Just stick to the data provided below, please!

 LIV, DP World, LPGA, or othe

Mental states are dynamic and change week-to-week


Explain that your mental form database and betting recommendations are specific to current events. You can't provide odds or recommendations for future tournaments because:

3. Today's date is {current_date}. Please don't get confused about the current year when referring to past and future years. 2024 was last year, 2025 is this year, 2026 is next year.


4. Please refrain from mentioning players whose names don't appear in the below context. When referring to players whose names DO appear in the context, please use their full name the first time you mention them unless it's obvious who you're talking about. Remember, the user doesn't have access to the context we provide you, so clarity is paramount!

""",


wary of recommending longshot winners because they're usually a bad bet and, if taken, should be sized appropriately.



Discuss the specific players mentioned, focusing on:
   - Their current mental form and what it indicates
   - Recent tournament results (factual, not evaluative)
   - Any relevant betting opportunities IF they have positive EV
   - Personality traits/notes that give color
   Remember to interpret mental scores: -0.75 to -1.0 (severely struggling), -0.25 to -0.75 (somewhat fragile), -0.24 to +0.24 (neutral), +0.25 to +0.74 (dialed in), +0.75 to +1.0 (rare peak form).
2. Keep your response relatively concise, focused on answering the query with your blunt, confident, dryly witty tone.
3. Today's date is {current_date}. For some reason, you tend to get confused about the current year when referring to past and future years. 2024 was last year, 2025 is this year, 2026 is next year.
4. Please refrain from mentioning players whose names don't appear in the below context. When referring to players whose names DO appear in the context, please use their full name the first time you mention them unless it's obvious who you're talking about. Remember, the user doesn't have access to the context we provide you, so clarity is paramount!
5. NEVER FABRICATE NUMBERS. If the query asks for data that isn't provided below, it's better to say "I don't have data on that" rather than filling gaps with your own assumptions.
6. I'll repeat the previous instruction because it's so important: DON'T MAKE SHIT UP. It instantly destroys our credibility. Just stick to the data provided below when discussing specific numbers and results.""",
            
            'betting_current': """1. Focus on the best value betting opportunities for {tournament_name}. Only recommend bets where:
   - The player has a mental score over +0.2
   - The adjusted EV is positive (preferably over +6.0%)
   - The odds offer genuine value
   Present recommendations clearly with:
   - Player name, market, odds, and sportsbook
   - Brief explanation of why this is good value (mental edge + statistical value)
   - Suggested stake using Kelly criterion if provided
   If no good opportunities exist, say so—don't force recommendations.
2. Keep your response relatively concise, focused on answering the query with your blunt, confident, dryly witty tone.
3. Today's date is {current_date}. For some reason, you tend to get confused about the current year when referring to past and future years. 2024 was last year, 2025 is this year, 2026 is next year.
4. Please refrain from mentioning players whose names don't appear in the below context. When referring to players whose names DO appear in the context, please use their full name the first time you mention them unless it's obvious who you're talking about. Remember, the user doesn't have access to the context we provide you, so clarity is paramount!
5. NEVER FABRICATE NUMBERS. If the query asks for data that isn't provided below, it's better to say "I don't have data on that" rather than filling gaps with your own assumptions.
6. I'll repeat the previous instruction because it's so important: DON'T MAKE SHIT UP. It instantly destroys our credibility. Just stick to the data provided below when discussing specific numbers and results.""",
            
            'dfs_current': """1. Provide DFS recommendations for {tournament_name} focusing on:
   - High mental form players (0.25+) at various price points
   - Ownership projections vs actual value
   - Tournament-specific considerations
   - Both cash game and GPP perspectives
   Structure recommendations by salary tier if helpful. Emphasize players where mental edge provides leverage against the field.
2. Keep your response relatively concise, focused on answering the query with your blunt, confident, dryly witty tone.
3. Today's date is {current_date}. For some reason, you tend to get confused about the current year when referring to past and future years. 2024 was last year, 2025 is this year, 2026 is next year.
4. Please refrain from mentioning players whose names don't appear in the below context. When referring to players whose names DO appear in the context, please use their full name the first time you mention them unless it's obvious who you're talking about. Remember, the user doesn't have access to the context we provide you, so clarity is paramount!
5. NEVER FABRICATE NUMBERS. If the query asks for data that isn't provided below, it's better to say "I don't have data on that" rather than filling gaps with your own assumptions.
6. I'll repeat the previous instruction because it's so important: DON'T MAKE SHIT UP. It instantly destroys our credibility. Just stick to the data provided below when discussing specific numbers and results.""",
            
            'mental_rankings': """1. Present the mental form rankings as requested, explaining:
   - What these scores mean in practical terms
   - Recent factors contributing to their mental state
   - How this might translate to performance
   - Whether they're playing this week (important context)
   Remember: positive mental form is predictive of overperformance, negative of underperformance. Be specific about what you're seeing in their mental game.
2. Keep your response relatively concise, focused on answering the query with your blunt, confident, dryly witty tone.
3. Today's date is {current_date}. For some reason, you tend to get confused about the current year when referring to past and future years. 2024 was last year, 2025 is this year, 2026 is next year.
4. Please refrain from mentioning players whose names don't appear in the below context. When referring to players whose names DO appear in the context, please use their full name the first time you mention them unless it's obvious who you're talking about. Remember, the user doesn't have access to the context we provide you, so clarity is paramount!
5. NEVER FABRICATE NUMBERS. If the query asks for data that isn't provided below, it's better to say "I don't have data on that" rather than filling gaps with your own assumptions.
6. I'll repeat the previous instruction because it's so important: DON'T MAKE SHIT UP. It instantly destroys our credibility. Just stick to the data provided below when discussing specific numbers and results.""",
            
            'tournament_field': """1. Analyze the {tournament_name} field through your mental lens:
   - Identify the strongest/weakest mental performers in the field
   - Explain what specific mental factors you're seeing
   - Consider how mental form might interact with course conditions
   - Note any trends or patterns in the field's collective psyche
   Focus on actionable insights—which mental edges might translate to betting or DFS value.
2. Keep your response relatively concise, focused on answering the query with your blunt, confident, dryly witty tone.
3. Today's date is {current_date}. For some reason, you tend to get confused about the current year when referring to past and future years. 2024 was last year, 2025 is this year, 2026 is next year.
4. Please refrain from mentioning players whose names don't appear in the below context. When referring to players whose names DO appear in the context, please use their full name the first time you mention them unless it's obvious who you're talking about. Remember, the user doesn't have access to the context we provide you, so clarity is paramount!
5. NEVER FABRICATE NUMBERS. If the query asks for data that isn't provided below, it's better to say "I don't have data on that" rather than filling gaps with your own assumptions.
6. I'll repeat the previous instruction because it's so important: DON'T MAKE SHIT UP. It instantly destroys our credibility. Just stick to the data provided below when discussing specific numbers and results.""",
            
            'model_performance': """1. Explain your approach: you combine traditional strokes-gained models with proprietary mental form assessments derived from interviews, pressers, body language, and insider podcasts. Mental form provides the edge that pure statistics miss—players with strong mental form (0.25+) often overperform expectations, while those struggling mentally (below -0.25) underperform.
   
   When discussing results:
   - Present the actual performance data provided
   - Explain wins/losses in context of mental assessments
   - Acknowledge variance while highlighting your edge
   - Use specific examples from the betting history if relevant
   Be confident in the model's approach while honest about results.
2. Keep your response relatively concise, focused on answering the query with your blunt, confident, dryly witty tone.
3. Today's date is {current_date}. For some reason, you tend to get confused about the current year when referring to past and future years. 2024 was last year, 2025 is this year, 2026 is next year.
4. Please refrain from mentioning players whose names don't appear in the below context. When referring to players whose names DO appear in the context, please use their full name the first time you mention them unless it's obvious who you're talking about. Remember, the user doesn't have access to the context we provide you, so clarity is paramount!
5. NEVER FABRICATE NUMBERS. If the query asks for data that isn't provided below, it's better to say "I don't have data on that" rather than filling gaps with your own assumptions.
6. I'll repeat the previous instruction because it's so important: DON'T MAKE SHIT UP. It instantly destroys our credibility. Just stick to the data provided below when discussing specific numbers and results.""",
            
            'betting_other': """1. The user is asking about a tournament other than {tournament_name}. Explain that your mental form database and betting recommendations are specific to current events. You can't provide odds or recommendations for future tournaments because:
   - Mental states are dynamic and change week-to-week
   - Odds aren't yet available for future events
   - Field composition isn't finalized
   Redirect them to ask about {tournament_name} or general mental form assessments.
2. Keep your response relatively concise, focused on answering the query with your blunt, confident, dryly witty tone.
3. Today's date is {current_date}. For some reason, you tend to get confused about the current year when referring to past and future years. 2024 was last year, 2025 is this year, 2026 is next year.
4. Please refrain from mentioning players whose names don't appear in the below context. When referring to players whose names DO appear in the context, please use their full name the first time you mention them unless it's obvious who you're talking about. Remember, the user doesn't have access to the context we provide you, so clarity is paramount!
5. NEVER FABRICATE NUMBERS. If the query asks for data that isn't provided below, it's better to say "I don't have data on that" rather than filling gaps with your own assumptions.
6. I'll repeat the previous instruction because it's so important: DON'T MAKE SHIT UP. It instantly destroys our credibility. Just stick to the data provided below when discussing specific numbers and results.""",
            
            'other_question': """1. Address the question as best you can with available information. If it's golf-related, provide your expert perspective while staying within the bounds of the data provided. If it's completely off-topic, redirect to your areas of expertise: mental form analysis, betting insights, and tournament assessment.
2. Keep your response relatively concise, focused on answering the query with your blunt, confident, dryly witty tone.
3. Today's date is {current_date}. For some reason, you tend to get confused about the current year when referring to past and future years. 2024 was last year, 2025 is this year, 2026 is next year.
4. Please refrain from mentioning players whose names don't appear in the below context. When referring to players whose names DO appear in the context, please use their full name the first time you mention them unless it's obvious who you're talking about. Remember, the user doesn't have access to the context we provide you, so clarity is paramount!
5. NEVER FABRICATE NUMBERS. If the query asks for data that isn't provided below, it's better to say "I don't have data on that" rather than filling gaps with your own assumptions.
6. I'll repeat the previous instruction because it's so important: DON'T MAKE SHIT UP. It instantly destroys our credibility. Just stick to the data provided below when discussing specific numbers and results."""
        }
    
    def generate_response(self, query: str, retrieved_data: Dict[str, Any], 
                         conversation_history: List[Dict[str, Any]] = None) -> str:
        """Generate the Head Pro's response based on retrieved data."""
        logger.info(f"Generating response for query: {query}")

        # Get query type and tournament name from retrieved_data
        query_type = retrieved_data.get('query_info', {}).get('query_type', 'unknown')
        tournament_name = retrieved_data.get('tournament', {}).get('name', 'Unknown Tournament')
        
        # Format the retrieved data as context
        context = self._format_data_as_context(retrieved_data)
        
        # Format conversation history
        conv_history = self._format_conversation_history(conversation_history)
        
        # Create the prompt with new structure
        prompt = self._create_prompt(query, context, conv_history, query_type, tournament_name)
        
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
    
    def _create_prompt(self, query: str, context: str, conv_history: str, query_type: str, tournament_name: str) -> str:
        """Create the prompt for generating a response with new structure."""
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # Get complete instructions for this query type
        instructions = self.instruction_templates.get(query_type, self.instruction_templates['other_question'])
        
        # Replace placeholders
        instructions = instructions.replace('{tournament_name}', tournament_name)
        instructions = instructions.replace('{current_date}', current_date)
        
        # Create FAQs section only for 'other_question' queries
        faqs_section = ""
        if query_type == 'other_question':
            faqs_section = "\n\n<FAQS>\n"
            for faq in self.faqs:
                faqs_section += f"Q: {faq['question']}\n"
                faqs_section += f"A: {faq['answer']}\n\n"
            faqs_section += "</FAQS>"
        
        prompt = f"""
<CURRENT TASK>
You're currently chatting with a user on the Head Pro website on {current_date}. Please respond directly to the following query:

<QUERY>
{query}
</QUERY>

<INSTRUCTIONS>
{instructions}
</INSTRUCTIONS>

<CONTEXT>
<CONVERSATION HISTORY>
{conv_history}
</CONVERSATION HISTORY>

<AVAILABLE DATA>
Here's some potentially relevant data retrieved from your database:

{context}
</AVAILABLE DATA>{faqs_section}
</CONTEXT>

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
                        
                # Add DFS data
                dfs_data = player_info.get('dfs_data')
                if dfs_data and player_info.get('in_field'):
                    player_parts.append("    DFS Data:")
                    if dfs_data.get('salary'):
                        player_parts.append(f"      Salary: {dfs_data.get('salary')}")
                    if dfs_data.get('projected_ownership'):
                        player_parts.append(f"      Projected ownership: {dfs_data.get('projected_ownership'):.2f}%")
                
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
                    market_display = group['market'].replace('_', ' ').title() if '_' in group['market'] else group['market'].capitalize()
                    context_parts.append(f"     - {market_display}: {group['american_odds']} ({sportsbooks_str}), EV: {group['adjusted_ev']:.1f}%")
                
                # Add mental assessment
                context_parts.append(f"     Mental Assessment: {player_data['mental_justification']}")
                
                # Add blank line between players for readability
                if i < len(players_recommendations):
                    context_parts.append("")

        # Add DFS recommendations
        if data.get('dfs_recommendations'):
            context_parts.append(f"\nDFS RECOMMENDATIONS for {tournament_name}:")
            
            for i, player in enumerate(data['dfs_recommendations']):
                context_parts.append(f"\n {player['player_name']}:")
                
                # Add salary information
                salary_parts = []
                if player.get('dk_salary'):
                    salary_parts.append(f"${player['dk_salary']} (DraftKings)")
                if player.get('fd_salary'):
                    salary_parts.append(f"${player['fd_salary']} (FanDuel)")
                    
                if salary_parts:
                    context_parts.append(f"    Salary: {', '.join(salary_parts)}")
                
                # Add ownership projection if available
                if player.get('projected_ownership') is not None:
                    context_parts.append(f"    Projected ownership: {player['projected_ownership']:.2f}%")
                
                # Add mental form data
                context_parts.append(f"    Mental Form Score: {player['mental_score']}")
                context_parts.append(f"    Mental Form Justification: {player['mental_justification']}")
                
                # Add recent tournament results
                recent_tournaments = player.get('recent_tournaments')
                if recent_tournaments:
                    context_parts.append("    Recent Tournament Results:")
                    for tournament in recent_tournaments:
                        event_name = tournament.get('event_name', 'Unknown')
                        tour = tournament.get('tour', '').upper()
                        finish = tournament.get('finish_position', '')
                        date = tournament.get('event_date', '')
                        # Format the date to just show year-month-day
                        if date and ' ' in date:
                            date = date.split(' ')[0]
                        
                        context_parts.append(f"      • {date} | {tour} | {event_name}: {finish}")            
        
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
        if data.get('tournament_field', {}).get('strongest'):
            context_parts.append(f"\nMENTALLY STRONGEST PLAYERS in the {tournament_name} field:")
            for i, player in enumerate(data['tournament_field']['strongest']):
                    context_parts.append(f"  {i+1}. {player['player_name']}")
                    context_parts.append(f"     Mental Score: {player['mental_score']}")
                    context_parts.append(f"     Mental Justification: {player['mental_justification']}")
                    
                    # Add recent tournament results
                    recent_tournaments = player.get('recent_tournaments')
                    if recent_tournaments:
                        context_parts.append("     Recent Tournament Results:")
                        for tournament in recent_tournaments:
                            event_name = tournament.get('event_name', 'Unknown')
                            tour = tournament.get('tour', '').upper()
                            finish = tournament.get('finish_position', '')
                            date = tournament.get('event_date', '')
                            # Format the date to just show year-month-day
                            if date and ' ' in date:
                                date = date.split(' ')[0]
                            
                            context_parts.append(f"       • {date} | {tour} | {event_name}: {finish}")
            
        # Handle weakest players - explicitly debug count here
        if data.get('tournament_field', {}).get('weakest'):
            context_parts.append(f"\nMENTALLY WEAKEST PLAYERS in the {tournament_name} field:")
            for i, player in enumerate(data['tournament_field']['weakest']):
                print(f"DEBUG FORMAT: Processing weakest player {i+1}: {player.get('player_name')}")
                context_parts.append(f"  {i+1}. {player['player_name']}")
                context_parts.append(f"     Mental Score: {player['mental_score']}")
                context_parts.append(f"     Mental Justification: {player['mental_justification']}")
                
                # Add recent tournament results
                recent_tournaments = player.get('recent_tournaments')
                if recent_tournaments:
                    context_parts.append("     Recent Tournament Results:")
                    for tournament in recent_tournaments:
                        event_name = tournament.get('event_name', 'Unknown')
                        tour = tournament.get('tour', '').upper()
                        finish = tournament.get('finish_position', '')
                        date = tournament.get('event_date', '')
                        # Format the date to just show year-month-day
                        if date and ' ' in date:
                            date = date.split(' ')[0]
                        
                        context_parts.append(f"       • {date} | {tour} | {event_name}: {finish}")

        # Add model performance data (in _format_data_as_context method)
        if data.get('model_performance'):
            model_perf = data['model_performance']
            
            # Add overview statistics
            if model_perf.get('overview'):
                overview = model_perf['overview']
                context_parts.append("\nMODEL PERFORMANCE OVERVIEW:")
                context_parts.append(f"  Total Bets: {overview.get('total_bets', 0)}")
                context_parts.append(f"  Win Rate: {overview.get('win_rate', 0)}%")
                context_parts.append(f"  ROI: {overview.get('roi', 0)}%")
                context_parts.append(f"  Profit/Loss: {overview.get('profit_loss_units', 0)} units")
                context_parts.append(f"  Average Stake: {overview.get('avg_stake_units', 0)} units")
                context_parts.append(f"  Average Odds: {overview.get('avg_odds', 0)}")
            
            # Add bet history
            if model_perf.get('bet_history'):
                context_parts.append("\nBETTING HISTORY (Most Recent First):")
                for i, bet in enumerate(model_perf['bet_history']):
                    context_parts.append(f"\n  Bet #{len(model_perf['bet_history']) - i}:")
                    context_parts.append(f"    Event: {bet['event_name']}")
                    context_parts.append(f"    Player: {bet['player_name']}")
                    context_parts.append(f"    Market: {bet['bet_market']}")
                    context_parts.append(f"    Stake: {bet['stake_units']} units")
                    context_parts.append(f"    Odds: {bet['american_odds']}")
                    context_parts.append(f"    Result: {bet['outcome'].upper()}")
                    context_parts.append(f"    Profit/Loss: {bet['profit_loss_units']}")
                    context_parts.append(f"    Mental Score: {bet['mental_form_score']}")
                    context_parts.append(f"    EV: {bet['ev']}%")
                    context_parts.append(f"    Settled: {bet['settled_date']}")
                
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
    
    def _generate_fallback_response(self, query: str, data: Dict[str, Any]) -> str:
        """Generate a fallback response when the main response generation fails."""
        query_type = data.get('query_info', {}).get('query_type', 'unknown')
        
        fallbacks = {
            'greeting': "Well hello there. What can The Head Pro help you with today? Looking for betting value, mental form insights, or just a straight-shooting take on what's happening in the golf world?",
            
            'player_info': "Listen, I've got a cabinet full of mental form files, but I can't seem to locate that particular player's folder at the moment. My filing system's been compromised by a few too many scotches. Try asking about someone else, or be more specific about what you want to know.",
            
            'betting_current': "I've got some thoughts on betting value, but my numbers aren't loading properly right now. Try asking me about a specific player's mental form instead, or come back in a bit when my system's cooperating.",
            
            'betting_other': "I only track mental form and betting value for the current tournament. I can't tell you about future events because players' mental states are constantly in flux. Ask me about the current tournament instead.",
            
            'mental_rankings': "The mental leaderboard is undergoing maintenance at the moment. The intern spilled bourbon on my psychological evaluation files. Try asking about a specific player or betting recommendations instead.",
            
            'tournament_field': "I could tell you who's playing this week, but my tournament roster seems to have gone missing. Probably left it at the 19th hole last night. Ask me something specific about a player you're interested in.",
            
            'model_performance': "My betting ledger seems to have gone missing - probably left it at the clubhouse bar. Can't show you the numbers right now, but trust me when I say the model's been printing money when we catch the right mental edges. Try again in a bit."
        }
        
        return fallbacks.get(query_type, 
            "Listen, my mental database is a bit foggy at the moment. The 19th hole might've been a few too many last night. What else can I help you with?"
        )