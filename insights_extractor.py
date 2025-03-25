"""
Extract player insights from transcripts using Claude API and store them in the database.
"""

import os
import argparse
import anthropic
import datetime
import sqlite3
from dotenv import load_dotenv

load_dotenv()

def read_transcript(file_path):
    """Read the transcript file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def create_claude_prompt(transcript, event_name):
    """Create a prompt for Claude to extract insights"""
    prompt = f"""
You are a specialized analyzer extracting QUALITATIVE insights from professional golf podcast transcripts. Your mission is to identify intangible factors that traditional statistical models like Data Golf cannot capture, with special focus on mental game elements.

EXTRACTION GUIDELINES:

1. TARGET THESE HIGH-VALUE QUALITATIVE FACTORS:

   MENTAL & EMOTIONAL STATE:
   - Confidence level and changes (lost/gained confidence)
   - Emotional regulation on course (calmness or frustration)
   - Pressure handling (clutch performance or collapse patterns)
   - Focus and concentration (distraction or enhanced presence)
   - On-course emotional outbursts (club throwing, visible anger)
   - Body language observations from commentators

   PERSONAL & PROFESSIONAL ENVIRONMENT:
   - Life events (family changes, relocations, personal challenges)
   - Team dynamics (caddie relationships, coach changes)
   - Equipment changes and their specific effects
   - Physical condition (injuries, fitness improvements, fatigue)
   - Work ethic and practice quality (not just quantity)
   - Strategic approach changes (course management, risk assessment)

2. STRICTLY EXCLUDE STATISTICAL INFORMATION:
   - Strokes gained metrics and other performance statistics
   - Historical tournament results
   - Course fit based on statistical patterns
   - Rankings or world position discussions
   - General strategy discussions without player-specific insights

3. EXTRACTION QUALITY CONTROLS:
   - Maintain context that explains WHY the insight matters
   - Only extract genuine insights - quality over quantity
   - Specify the source if mentioned (player, coach, analyst)

For each legitimate qualitative insight, format your response exactly as follows:

<player>
[PLAYER NAME]
</player>
<insight>
[DETAILED QUALITATIVE INSIGHT INCLUDING RELEVANT CONTEXT]
</insight>

While this transcript may discuss the {event_name}, extract ALL player insights regardless of whether they relate to this specific event. If a player is mentioned but no meaningful qualitative insights are provided, do not include them.

Here is the transcript:
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
        # Extract last name for searching
        name_parts = name.split()
        if len(name_parts) > 1:
            last_name = name_parts[-1].lower()
            cursor.execute('''
            SELECT * FROM players 
            WHERE LOWER(name) LIKE ?
            ''', (f'%{last_name},%',))
            players = cursor.fetchall()

            # If multiple players match, try filtering by full name
            if len(players) > 1:
                players = [p for p in players if name.lower() in p[1].lower()]  # Assuming name is in index 1
                
            if players:
                return players[0]  # Return best match
    
        # If no match by last name, try full name partial match
        cursor.execute('''
        SELECT * FROM players 
        WHERE LOWER(name) LIKE ?
        ''', (f'%{name.lower()}%',))
    
    else:
        # Exact match
        cursor.execute('''
        SELECT * FROM players 
        WHERE LOWER(name) = ?
        ''', (name.lower(),))
    
    players = cursor.fetchall()
    
    if players:
        return players[0]  # Still returns first match, but filtering is improved
    
    # Handle special cases
    special_cases = {
        "JT POSTON": "Poston, J.T.",
        "NICOLAI HØJGAARD": "Hojgaard, Nicolai",
        "NIKOLAI HØJGAARD": "Hojgaard, Nicolai",
        "NIKOLAI HOJGAARD": "Hojgaard, Nicolai",
        "RASMUS HØJGAARD": "Hojgaard, Rasmus",
        "AILANO GRILLO": "Grillo, Emiliano",
        "AILANO GRIO": "Grillo, Emiliano",
        "EMILIANO GRIO": "Grillo, Emiliano",
        "CRISTOBAL DEL SOLAR": "Del Solar, Cristobal",
    }
    
    if name.upper() in special_cases:
        special_case_name = special_cases[name.upper()]
        cursor.execute('''
        SELECT * FROM players 
        WHERE LOWER(name) = ?
        ''', (special_case_name.lower(),))
        players = cursor.fetchall()
        if players:
            return players[0]
    
    return None


def add_insight(conn, player_id, insight_text, source, event_name):
    """
    Add a new insight for a player.
    
    Args:
        conn: SQLite connection
        player_id: ID of the player in the database
        insight_text: The insight text
        source: Source of the insight (podcast name, etc.)
        event_name: Name of the tournament
        
    Returns:
        ID of the new insight
    """
    cursor = conn.cursor()
    
    # Get current date
    current_date = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # Insert the insight
    cursor.execute('''
    INSERT INTO insights 
    (player_id, text, source, source_type, content_title, date)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (player_id, insight_text, source, "podcast", event_name, current_date))
    
    # Get the ID of the new insight
    insight_id = cursor.lastrowid
    
    # Set sentiment last_updated to NULL to trigger recalculation
    cursor.execute('''
    UPDATE sentiment
    SET last_updated = NULL
    WHERE player_id = ?
    ''', (player_id,))
    
    return insight_id

def save_unmatched_insights(unmatched_insights, event_name, transcript_path):
    """
    Save unmatched player insights to a separate file in the 'insights' directory.
    """
    if not unmatched_insights:
        return None
    
    # Create insights directory if it doesn't exist
    os.makedirs("insights", exist_ok=True)
    
    # Get the transcript filename without path and extension
    transcript_filename = os.path.splitext(os.path.basename(transcript_path))[0]
    
    # Create a clean event name (lowercase, underscores)
    clean_event_name = event_name.lower().replace(' ', '_').replace("'", "").replace('"', '')
    
    # Create filename with event name, transcript filename, and date
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    filename = f"insights/unmatched_{clean_event_name}_{transcript_filename}_{date_str}.txt"
    
    # Write unmatched insights to file
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"Unmatched insights for {event_name}\n")
        f.write(f"Transcript: {transcript_path}\n")
        f.write(f"Date: {date_str}\n\n")
        
        for insight in unmatched_insights:
            f.write(f"Player: {insight['player_name']}\n")
            f.write(f"Insight: {insight['insight']}\n\n")
    
    return filename

def main():
    parser = argparse.ArgumentParser(description="Extract player insights from transcripts using Claude API")
    parser.add_argument("--transcript", required=True, help="Path to transcript file")
    parser.add_argument("--event_name", required=True, help="Name of the golf event")
    parser.add_argument("--source", required=True, help="Source of the insights (e.g., podcast name)")
    parser.add_argument("--api_key", help="Claude API key (or set ANTHROPIC_API_KEY env variable)")
    parser.add_argument("--db_path", default="data/db/sentiment.db", help="Path to SQLite database")
    parser.add_argument("--output", help="Output file for Claude's raw response")
    
    args = parser.parse_args()
    
    # Get API key from args or environment
    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
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
            add_insight(conn, player_id, insight_text, args.source, args.event_name)
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
        unmatched_file = save_unmatched_insights(unmatched_insights, args.event_name, args.transcript)
        print(f"\nWarning: {len(unmatched_insights)} players not found in database")
        print(f"Unmatched insights saved to: {unmatched_file}")
        print("Unmatched players:")
        for item in unmatched_insights:
            print(f"- {item['player_name']}")

if __name__ == "__main__":
    main()