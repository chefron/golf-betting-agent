"""
Extract player insights from transcripts using Claude API and store them in the database.
"""

import os
import argparse
import anthropic
import datetime
import sqlite3
from dotenv import load_dotenv

from db_utils import add_insight

load_dotenv()

def read_transcript(file_path):
    """Read the transcript file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def create_claude_prompt(transcript, event_name):
    """Create a prompt for Claude to extract insights"""
    # Get current date
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    prompt = f"""
You are a sports psychologist extracting QUALITATIVE insights about professional golfers from media sources. Focus solely on INTANGIBLE factors statistical models cannot capture, especially mental aspects. Ignore performance results. You don't care about stats or scores. 

Focus on QUALITY insights OVER QUANTITY - it's OK if few or no substantive insights exist in the source.

EXTRACTION GUIDELINES:

1. TARGET THESE HIGH-VALUE QUALITATIVE FACTORS:

   MENTAL & EMOTIONAL STATE:
   - Confidence level and changes (directly expressed or observed, not assumed from performance results)
   - Emotional regulation on course (observed reactions, not inferred from playing well/poorly)
   - Pressure handling (specific mental responses, not just performance outcomes)
   - Focus and concentration (as directly discussed or observed)
   - On-course emotional outbursts (specific incidents described)
   - Body language observations (only when explicitly described)

   PERSONAL & PROFESSIONAL ENVIRONMENT:
   - Physical condition (injuries, fitness improvements, fatigue)
   - Life events (family changes, relocations, personal challenges)
   - Team dynamics (caddie relationships, coach changes)
   - Equipment changes and their specific effects
   - Work ethic and practice quality (including practice rounds)
   - Strategic approach changes (course management, risk assessment)

2. STRICTLY EXCLUDE:
   - Statistics-based evaluations
   - Skill assessments based on results
   - Course fit discussions
   - Rankings or world position discussions
   - Vague statements of optimism or standard sports cliches that don't give us any true insight into the golfer

3. QUALITY CONTROLS:
   - Only extract genuine qualitative insights - quality over quantity!
   - DO NOT evaluate or interpret the insight - simply extract and lightly polish the information as presented. Be objective!
   - Specify the source if mentioned (player, coach, analyst), as well as any tournaments. Context is important.
   - You may lightly polish the language for clarity and readability
   - When time references are ambiguous, interpret them relative to today's date ({today})

For each substantive qualitative insight, format your response exactly as follows:

<player>
[PLAYER NAME]
</player>
<insight>
[DETAILED QUALITATIVE INSIGHT INCLUDING RELEVANT CONTEXT]
</insight>

While this transcript may discuss the {event_name}, extract all substantive qualitative player insights regardless of whether they relate to this specific event. Each insight may only be assigned to one golfer. When possible, include specific details for each insight such as the tournament names, timing information (e.g., "last week at the 2025 Masters," "during Valspar's final round"), golfers' full names, and any other relevant context. This timeline information will help another LLM establish patterns in the player's mental state, physical health, and other intangibles over time.

Remember, QUALITY OVER QUANTITY! Be selective, and don't infer anything from performance results!

Without further ado, here is the transcript:
{transcript}
"""
    return prompt

def query_claude(prompt, api_key):
    """Query Claude API to extract insights"""
    client = anthropic.Anthropic(api_key=api_key)
    
    message = client.messages.create(
        model="claude-3-7-sonnet-20250219",
        max_tokens=4000,
        temperature=0,
        system="You extract precise, structured insights about professional golfers from podcast transcripts.",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    # Return the text content from the message
    return message.content[0].text

def parse_claude_response(response):
    """Parse Claude's response to extract player insights"""
    insights = []
    
    # Find all player/insight pairs using simple string parsing
    player_segments = response.split("<player>")
    
    for segment in player_segments[1:]:  # Skip the first split which is before any <player> tag
        try:
            # Extract player name and clean it
            player_name_raw = segment.split("</player>")[0]
            player_name = player_name_raw.strip()
            
            # Extract insight and clean it as well
            insight_text_raw = segment.split("<insight>")[1].split("</insight>")[0]
            insight_text = insight_text_raw.strip()
            
            insights.append({
                "player_name": player_name,
                "insight": insight_text
            })
        except IndexError:
            continue  # Skip malformed segments
    
    return insights

def get_player_by_name(conn, name, fuzzy=True):
    cursor = conn.cursor()
    
    if fuzzy:
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
                return players[0]
            
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
                            return player
            
        # Try a simple contains match as fallback
        cursor.execute('SELECT * FROM players WHERE LOWER(name) LIKE ?', (f"%{name_lower}%",))
        players = cursor.fetchall()
        if players:
            return players[0]
    
    else:
        # Exact match - unchanged
        cursor.execute('SELECT * FROM players WHERE LOWER(name) = ?', (name.lower(),))
        players = cursor.fetchall()
        if players:
            return players[0]
    
    # Handle special cases
    special_cases = {
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
    
    if name.upper() in special_cases:
        special_case_name = special_cases[name.upper()]
        cursor.execute('SELECT * FROM players WHERE LOWER(name) = ?', (special_case_name.lower(),))
        players = cursor.fetchall()
        if players:
            return players[0]
    
    return None

def save_unmatched_insights(unmatched_insights, event_name, transcript_path, source, episode_title, content_url):
    """
    Save unmatched player insights to a separate file in the 'insights' directory.
    Includes all metadata needed to easily add these insights later.
    """
    if not unmatched_insights:
        return None
    
    # Create insights directory if it doesn't exist
    os.makedirs("insights", exist_ok=True)
    
    # Get the transcript filename without path and extension
    transcript_filename = os.path.splitext(os.path.basename(transcript_path))[0]
    
    # Create filename with source, transcript filename, and date
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    source_slug = source.lower().replace(' ', '_').replace("'", "").replace('"', '')
    filename = f"insights/unmatched_{source_slug}_{transcript_filename}_{date_str}.txt"
    
    # Write unmatched insights to file
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"Unmatched insights for {event_name}\n")
        f.write(f"Transcript: {transcript_path}\n")
        f.write(f"Source: {source}\n")
        f.write(f"Episode Title: {episode_title or 'N/A'}\n")
        f.write(f"Content URL: {content_url or 'N/A'}\n")
        f.write(f"Date: {date_str}\n\n")
        
        for insight in unmatched_insights:
            f.write(f"Player: {insight['player_name']}\n")
            f.write(f"Insight: {insight['insight']}\n")
            # Add a way to easily copy-paste this insight with the correct player ID
            f.write("-- To add this insight, use: --\n")
            f.write("add_insight(\n")
            f.write("    player_id=PLAYER_ID_HERE,\n")
            f.write(f"    text=\"{insight['insight'].replace('"', '\\"')}\",\n")
            f.write(f"    source=\"{source}\",\n")
            f.write(f"    source_type=\"podcast\",\n")
            f.write(f"    content_title=\"{episode_title or ''}\",\n")
            f.write(f"    content_url=\"{content_url or ''}\",\n")
            f.write(f"    date=\"{date_str}\"\n")
            f.write(")\n\n")
    
    return filename

def main():
    parser = argparse.ArgumentParser(description="Extract player insights from transcripts using Claude API")
    parser.add_argument("--transcript", required=True, help="Path to transcript file")
    parser.add_argument("--event_name", required=True, help="Name of the golf event/tournament being discussed")
    parser.add_argument("--source", required=True, help="Source name (e.g., podcast name, publication)")
    parser.add_argument("--episode_title", help="Title of the specific episode or content piece")
    parser.add_argument("--content_url", help="URL to the source content (e.g., podcast episode URL)")
    parser.add_argument("--db_path", default="data/db/mental_form.db", help="Path to SQLite database")
    parser.add_argument("--output", help="Output file for Claude's raw response")
    
    args = parser.parse_args()
    
    # Get API key from args or environment
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: No Claude API key provided. Set ANTHROPIC_API_KEY env variable or use --api_key")
        return
    
    # Read transcript
    transcript = read_transcript(args.transcript)
    
    # Create prompt
    prompt = create_claude_prompt(transcript, args.event_name)
    
    # Query Claude
    print(f"Querying Claude to extract insights for {args.event_name}...")
    claude_response = query_claude(prompt, api_key)
    
    # Save raw response if requested
    if args.output:
        # Create insights directory if it doesn't exist
        os.makedirs("insights", exist_ok=True)
        
        # If args.output doesn't include a directory path, save it to the insights directory
        output_path = args.output
        if not os.path.dirname(output_path):
            output_path = os.path.join("insights", output_path)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(claude_response)
        print(f"Raw Claude response saved to {output_path}")
    
    # Parse response
    insights = parse_claude_response(claude_response)
    print(f"Extracted {len(insights)} player insights")
    
    # Connect to database
    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row
    
    # Track which players were updated and which weren't found
    updated_players = []
    unmatched_insights = []
    
    # For each insight, find the matching player and update
    for insight_item in insights:
        player_name = insight_item["player_name"]
        insight_text = insight_item["insight"]
        
        # Try to find the player in the database
        player = get_player_by_name(conn, player_name)
        
        if player:
            # Add insight
            player_id = player["id"]
            add_insight(
                player_id=player_id,
                text=insight_text,
                source=args.source,
                source_type="podcast",
                content_title=args.episode_title or "",
                content_url=args.content_url or "",
                date=datetime.datetime.now().strftime("%Y-%m-%d")
            )
            updated_players.append(player["name"])
            print(f"Added insight for {player['name']}")
        else:
            # Add to unmatched insights
            unmatched_insights.append({
                "player_name": player_name,
                "insight": insight_text
            })
            print(f"Could not find player: {player_name}")
    
    # Commit changes
    conn.commit()
    conn.close()
    
    # Print summary
    print(f"\nAdded {len(updated_players)} insights to database")
    if updated_players:
        print("Updated players:")
        for name in updated_players:
            print(f"- {name}")
    
    # Save unmatched insights if any
    if unmatched_insights:
        unmatched_file = save_unmatched_insights(
            unmatched_insights, 
            args.event_name, 
            args.transcript,
            args.source,
            args.episode_title,
            args.content_url
        )
        print(f"\nWarning: {len(unmatched_insights)} players not found in database")
        print(f"Unmatched insights saved to: {unmatched_file}")
        print("Unmatched players:")
        for item in unmatched_insights:
            print(f"- {item['player_name']}")

if __name__ == "__main__":
    main()