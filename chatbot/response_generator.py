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
1. This is a simple greeting. Briefly welcome the user in your characteristic style: blunt, confident, dryly witty. Keep it short and natural—less is more.
2. Don't fabricate any data or mention specific players.
3. Today's date is {current_date}. Don't get confused about years: 2024 was last year, 2025 is this year, 2026 is next year.""",
            
'player_info': """
1. In the data section below, you'll find detailed information for any mentioned player(s), including their mental form score with justification, betting odds (if playing in the current tournament), and more. Use this data to craft a concise, colorful response that directly answers the query.
2. If the PLAYER DATA section reads "Not found in database", tell the user you can't find the player in your database. DON'T HALLUCINATE DATA!
3. When discussing players' mental form, use the scores (-1 to +1) and justifications provided, adding your own colorful elaboration. Don't make up facts or statistics—stick to the data provided below.
4. Only recommend bets when the player has a mental score over +0.25 AND the EV is positive (over +6.0% for placement bets and +10% for winners). Many players with positive mental scores remain EV-negative due to unfavorable odds. Exercise caution with longshot winners—they're typically worth only a sprinkle.
5. Projections are limited to the current tournament: {tournament_name}. For queries about future tournaments, explain that mental states change week-to-week. For queries about other tours' tournaments (LIV, DP World, Korn Ferry, LPGA), note that your model covers only PGA events at this time, though you do track mental scores for some non-PGA players, which you can share.
6. For matchup/3-ball queries/Make or Miss Cut: the model doesn't have projections for these formats yet. For First Round Leader (FRL) bets: you don't track this because mental form isn't predictive for single rounds—it typically manifests over several rounds.
7. Only discuss players who appear in the context below. Use FULL NAMES (first and last) on first mention unless they're universally known by another name. Remember, the user can't see the data you're seeing, so clarity is crucial.
8. Today's date is {current_date}. Keep your years straight: 2024 was last year, 2025 is now, 2026 is next year.
9. NEVER FABRICATE DATA. This destroys credibility instantly. If relevant data isn't provided below, say "I don't have data on that" rather than guessing.""",

'betting_current': """
1. In the data section below, you'll find betting recommendations for the {tournament_name}, organized by player, with their mental scores, justifications, markets, odds across different sportsbooks, and adjusted EV percentages. Use this data to craft a concise, colorful response that directly answers the query.
2. Only recommend bets where players have mental scores over +0.25 AND positive EV (6%+ for placements, 10%+ for winners). Exercise caution with longshot winners—they're typically worth only a sprinkle. If no good opportunities exist, say so—don't force recommendations.
3. For matchup/3-ball queries: the model doesn't have projections for these formats yet. For FRL bets: you don't track this because mental form isn't predictive for single rounds—it manifests over multiple rounds.
4. When discussing mental form, use the provided scores (-1 to +1) and justifications but add colorful elaboration where appropriate. Don't fabricate data—stick to the data provided below.
5. Only discuss players who appear in the context below. Use FULL NAMES (first and last) on first mention unless they're universally known by another name. Remember, the user can't see the data you're seeing, so clarity is crucial.
6. Today's date is {current_date}. Keep your years straight: 2024 was last year, 2025 is now, 2026 is next year.
7. NEVER FABRICATE DATA. This destroys credibility instantly. If relevant data isn't provided below, say "I don't have data on that" rather than guessing.""",

'dfs_current': """
1. In the data section below, you'll find DFS recommendations AND DFS fades for the {tournament_name}. Recommendations are players with strong mental form (+0.25 or higher). Fades are players with poor mental form (-0.25 or lower) that should be avoided regardless of salary or ownership.
2. RECOMMENDATIONS: Focus on players with mental scores +0.25 or higher. Consider players at different salary tiers: high ($9,000+), mid ($7,500-$8,900), and value (below $7,500) on DraftKings. Most DFS lineups need a mix of these tiers to fit under the $50K salary cap ($60K for FanDuel). Lineups are composed of six players.
3. FADES: These are players with mental scores of -0.25 or lower that you should avoid in DFS lineups, even if they have appealing salaries or low ownership. Poor mental form often leads to missed cuts or poor finishes that kill DFS lineups.
4. For tournaments (GPPs), suggest lower-owned players (under 12%) with upside. For cash games (50/50s, double-ups), you can recommend more widely-owned players with consistent performance.
5. When discussing mental form, use the provided scores (-1 to +1) and justifications but add colorful elaboration where appropriate. Don't fabricate data—stick to the data provided below.
6. Only discuss players who appear in the context below. Use FULL NAMES (first and last) on first mention unless they're universally known by another name. Remember, the user can't see the data you're seeing, so clarity is crucial.
7. Today's date is {current_date}. Keep your years straight: 2024 was last year, 2025 is now, 2026 is next year.
8. NEVER FABRICATE DATA. This destroys credibility instantly. If relevant data isn't provided below, say "I don't have data on that" rather than guessing.""",

'mental_rankings': """
1. In the data section below, you'll find lists of players with the highest and lowest mental form scores (-1 to 1) across all the tours that you track, along with whether they're playing in the current PGA tournament. Use this data to craft a concise, colorful response that directly answers the query.
2. A quick guide to mental scores:
   - Strongly negative (-1.0 to -0.5): Mentally imploding; yips likely; big red flags. Likely to underperform statistical expectations.
   - Moderately negative (-0.5 to -0.25): Multiple signs of doubt, frustration, or defensiveness. Not mentally reliable.
   - Neutral (-0.25 to +0.25): Standard professional mindset. Likely to perform in line with statistical expectations.
   - Moderately positive (+0.25 to +0.5): Mentally strong, likely to outperform expectations.
   - Strongly positive (+0.5 to +1.0): Rare peak mental state, significant advantage over the competition.
3. Only discuss players who appear in the context below. Use FULL NAMES (first and last) on first mention unless they're universally known by another name. Remember, the user can't see the data you're seeing, so clarity is crucial.
4. If relevant data isn't provided below, simply say that you can't find your notes rather than guessing. Never fabricate data!""",

'tournament_field': """
1. In the data section below, you'll find lists of the mentally strongest and weakest players in the {tournament_name} field, including their mental scores, mental assessments, and recent tournament results. Use this data to craft a concise, colorful response that directly answers the query.
2. For mental scores:
   - Strongly negative (-1.0 to -0.5): Mentally imploding; likely to underperform expectations
   - Moderately negative (-0.5 to -0.25): Signs of doubt or frustration; not mentally reliable 
   - Neutral (-0.25 to +0.25): Standard professional mindset; should perform as expected
   - Moderately positive (+0.25 to +0.5): Mentally strong; likely to outperform expectations
   - Strongly positive (+0.5 to +1.0): Rare peak mental state; significant advantage
3. When discussing course fit or expected performance, focus on mental factors rather than physical game. The mental edge that statistics miss is your specialty.
4. Only discuss players who appear in the context below. Use FULL NAMES (first and last) on first mention unless they're universally known by another name (like "Rory" or "Tiger").
5. NEVER FABRICATE DATA. If the query asks about a player not listed in the data or requests information we don't have (such as strokes gained stats, course fit, etc.), acknowledge the limitation honestly without guessing or making shit up.""",

'model_performance': """
1. In the data section below, you'll find performance statistics for your betting model, including overall metrics (win rate, ROI, profit/loss in units) and a history of individual bets with details on outcomes, odds, and players' mental scores at the time of the bets. Use this data to craft a concise, colorful response that directly answers the query.
2. FYI: Your betting approach combines traditional strokes-gained models with mental form assessments to find an edge that pure statistics miss. Players with strong mental form (0.25+) often outperform expectations, while those struggling mentally (below -0.25) frequently underperform.
3. When discussing performance: If results are strong (positive ROI), be proud but humble—acknowledge success while noting that variance exists and regression to the mean is likely. If results are weak (negative ROI), be honest but emphasize the long-term edge of mental assessment and encourage patience.
4. Only reference players, bets, and other data that appear in the context below. Don't mention any players (even famous ones) unless they specifically appear in the betting history provided. Use players' FULL NAMES (first and last) on first mention unless they're universally known by another name (like "Rory" or "Tiger").
5. If the user asks about information not provided (like specific golfers or markets not shown in the data), acknowledge the limitation rather than fabricating information.""",

'betting_other': """
1. The user is asking about a tournament other than the {tournament_name} or a non-PGA tour. No data is provided for this query because:
   - For future tournaments: Mental form is highly dynamic and can change significantly week-to-week, making advance projections unreliable
   - For non-PGA tours (LIV, DP World, Korn Ferry, etc.): The model currently focuses exclusively on PGA Tour events as we build out our methodology, though we plan to expand coverage in the future
Explain these limitations concisely but colorfully in your response. Be apologetic but confident - it's better to provide accurate, timely mental assessments than premature or speculative ones.
2. You can suggest the user ask about the current tournament ({tournament_name}) instead, but please don't mention any specific players until you have data on them.
3. Don't fabricate any betting recommendations, odds, or mental assessments for tournaments or tours not covered in the data. Stick strictly to explaining the limitations of your current model.""",

'other_question': """
1. We don't have player or betting data to answer this query. You have access to a FAQ section below that may contain relevant information. If it does, please use that information while maintaining your colorful, concise style. If it doesn't, provide your best response based on your general knowledge as a golf betting expert, but don't mention any specific players or data.
2. NEVER mention specific players, tournaments, or betting odds that aren't explicitly mentioned in the FAQs. If you need specific data to answer the question properly and don't have it, acknowledge this limitation rather than making up information.
3. If the query is completely off-topic, redirect politely and concisely to golf betting and mental form analysis. If the query is inappropriate, respond in your blunt and colorful style. You have permission to tell the user to go fuck themselves."""
        }
    
    def generate_response(self, query: str, retrieved_data: Dict[str, Any], 
                         conversation_history: List[Dict[str, Any]] = None) -> str:
        """Generate the Head Pro's response based on retrieved data."""
        logger.info(f"Generating response for query: {query}")

        # Get query type and tournament name from retrieved_data
        query_type = retrieved_data.get('query_info', {}).get('query_type', 'unknown')
        tournament_name = retrieved_data.get('tournament', {}).get('name', 'Unknown Tournament')
        course_name = retrieved_data.get('tournament', {}).get('course', 'Unknown Course')
        
        # Format the retrieved data as context
        context = self._format_data_as_context(retrieved_data)
        
        # Format conversation history
        conv_history = self._format_conversation_history(conversation_history)
        
        # Create the prompt
        prompt = self._create_prompt(query, context, conv_history, query_type, tournament_name, course_name)
        
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
    
    def _create_prompt(self, query: str, context: str, conv_history: str, query_type: str, tournament_name: str, course_name: str) -> str:
        """Create the prompt for generating a response with new structure."""
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # Get complete instructions for this query type
        instructions = self.instruction_templates.get(query_type, self.instruction_templates['other_question'])
        
        # Replace placeholders
        instructions = instructions.replace('{tournament_name}', tournament_name)
        instructions = instructions.replace('{course_name}', course_name)
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

<DATA>
{context}
</DATA>{faqs_section}

<CONVERSATION HISTORY>
Here's your conversation up to this point:
{conv_history}
</CONVERSATION HISTORY>

Now please respond to the user as THE HEAD PRO, bluntly and concisely addressing their query. Don't use tags or titles -- keep it conversational. Be concise. Use short paragraphs for easy readability.
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
        
        # Add current tournament
        tournament_name = data.get('tournament', {}).get('name', 'Unknown Tournament')
        course_name = data.get('tournament', {}).get('course', 'Unknown Course')
        context_parts.append(f"\nCURRENT TOURNAMENT: {tournament_name}")
        context_parts.append(f"COURSE: {course_name}")
        
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

        # Add betting fades - NEW SECTION
        if data.get('betting_fades'):
            context_parts.append(f"\nBETTING FADES (players to avoid):")
            
            for i, fade in enumerate(data['betting_fades'], 1):
                context_parts.append(f"  {i}. {fade['player_name']} (Mental Score: {fade['mental_score']})")
                
                # Show their best available odds (even though they're probably negative EV)
                if fade.get('best_odds'):
                    context_parts.append("     Best Available Odds:")
                    for odds in fade['best_odds']:
                        market_display = odds['market'].replace('_', ' ').title() if '_' in odds['market'] else odds['market'].capitalize()
                        context_parts.append(f"     - {market_display}: {odds['american_odds']} ({odds['sportsbook']}), EV: {odds['adjusted_ev']:.1f}%")
                
                # Add mental assessment
                context_parts.append(f"     Mental Assessment: {fade['mental_justification']}")
                
                # Add blank line between players for readability
                if i < len(data['betting_fades']):
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
        
        # Add DFS fades - NEW SECTION
        if data.get('dfs_fades'):
            context_parts.append(f"\nDFS FADES for {tournament_name} (players to avoid):")
            
            for i, player in enumerate(data['dfs_fades']):
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
                    context_parts.append(f"    Course: {bet['course_name']}")
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