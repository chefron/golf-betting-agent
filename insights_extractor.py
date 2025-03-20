import os
import json
import argparse
import anthropic
from datetime import datetime
from dotenv import load_dotenv

from update_text_file import update_text_from_json  # Import the function to update the text file

load_dotenv()

def read_transcript(file_path):
    """Read the transcript file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def create_claude_prompt(transcript, event_name):
    """Create a prompt for Claude to extract insights"""
    prompt = f"""
You are tasked with analyzing a podcast transcript from professional golf insiders and media members to extract valuable player-specific betting insights for an upcoming golf event. Your goal is to identify and summarize key information that could be useful for making informed betting decisions.

The golf event you should focus on is:
<event>
{event_name}
</event>

Please follow these steps to analyze the transcript and extract betting insights:
1. Carefully read through the entire transcript, paying special attention to any mentions of the participating players.
2. Identify key pieces of information that could be relevant for betting purposes, such as:
   - Player form and recent performance
   - Course-specific advantages or disadvantages for certain players
   - Insider knowledge about a player's injuries, equipment changes, or mental state
   - The potential impact of weather conditions on certain players' tee times
3. For each relevant insight you identify, format your response as follows:

<player>
[PLAYER NAME]
</player>
<insight>
[DETAILED INSIGHT ABOUT THE PLAYER]
</insight>

Important guidelines:
- Present the insights as objective information without attributing them to specific hosts or analysts.
- Avoid phrases like "one host said," "the analysts believe," or "according to the podcast."
- Avoid direct quotes from the hosts. That said, direct quotes from golfers is acceptable and encouraged.
- Do not include external knowledge or make assumptions beyond what is stated or directly implied in the transcript.

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
    return message.content

def parse_claude_response(response):
    """Parse Claude's response to extract player insights"""
    insights = []
    
    # Convert response to string if it's a list
    if isinstance(response, list):
        response_text = " ".join([str(item) for item in response])
    else:
        response_text = str(response)
    
    # Find all player/insight pairs using simple string parsing
    player_segments = response_text.split("<player>")
    
    for segment in player_segments[1:]:  # Skip the first split which is before any <player> tag
        try:
            # Extract player name and clean it
            player_name_raw = segment.split("</player>")[0]
            # Remove the literal '\n' characters
            player_name = player_name_raw.replace('\\n', '').strip()
            
            # Extract insight and clean it as well
            insight_text_raw = segment.split("<insight>")[1].split("</insight>")[0]
            insight_text = insight_text_raw.replace('\\n', ' ').strip()
            
            insights.append({
                "player_name": player_name,
                "insight": insight_text
            })
        except IndexError:
            continue  # Skip malformed segments
    
    return insights

def match_player_name(input_name, database_players):
    """
    Match player names from Claude's response to database names.
    
    Args:
        input_name: The player name from Claude's insights (e.g., "TOMMY FLEETWOOD")
        database_players: Dictionary of player data from the JSON file
        
    Returns:
        player_id if found with high confidence, None otherwise
    """
    # Remove literal '\n' characters and strip whitespace
    clean_name = input_name.replace('\\n', '').strip()
    
    print(f"Trying to match player: '{clean_name}'")
    
    # Direct lookup (case insensitive)
    for player_id, player_data in database_players.items():
        db_name = player_data["name"].lower()
        if clean_name.lower() == db_name:
            print(f"Found exact match: '{clean_name}' with '{player_data['name']}'")
            return player_id
    
    # Direct "FIRST LAST" to "Last, First" conversion
    name_parts = clean_name.split()
    if len(name_parts) >= 2:
        # Get the last word as the last name
        last_name = name_parts[-1]
        # Get all words except the last as the first name
        first_name = ' '.join(name_parts[:-1])
        # Create the "Last, First" format
        reversed_name = f"{last_name}, {first_name}"
        
        # Try matching with this reversed name (case insensitive)
        for player_id, player_data in database_players.items():
            if reversed_name.lower() == player_data["name"].lower():
                print(f"Found match with reversed name: '{clean_name}' → '{reversed_name}' with '{player_data['name']}'")
                return player_id
    
    # Handle common variations and abbreviations with high confidence
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
    
    if clean_name.upper() in special_cases:
        special_case_name = special_cases[clean_name.upper()]
        for player_id, player_data in database_players.items():
            if special_case_name.lower() == player_data["name"].lower():
                print(f"Found special case match: '{clean_name}' → '{special_case_name}' with '{player_data['name']}'")
                return player_id
    
    # No match found with high confidence
    print(f"No match found for: '{clean_name}'")
    return None

def save_unmatched_insights(unmatched_insights, event_name, transcript_path):
    """
    Save unmatched player insights to a separate file in the 'insights' directory,
    using the transcript filename to make the output filename unique.
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
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"insights/unmatched_{clean_event_name}_{transcript_filename}_{date_str}.json"
    
    # Prepare output data structure with metadata
    output_data = {
        "event_name": event_name,
        "transcript_file": transcript_path,
        "date_processed": date_str,
        "unmatched_insights": unmatched_insights
    }
    
    # Save insights to JSON file
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2)
    
    return filename

def update_json_with_insights(insights, json_file):
    """Update the tournament JSON file with player insights using enhanced name matching"""
    # Load existing JSON data
    with open(json_file, 'r', encoding='utf-8') as f:
        tournament_data = json.load(f)
    
    # Track which players were updated and which weren't found
    updated_players = []
    unmatched_insights = []
    
    # For each insight, find the matching player and update
    for insight_item in insights:
        player_name = insight_item["player_name"]
        insight_text = insight_item["insight"]
        
        # Try to find the player in the database
        player_id = match_player_name(player_name, tournament_data["players"])
        
        if player_id:
            # Update insights (append if already exists)
            player_data = tournament_data["players"][player_id]
            existing_insight = player_data.get("insights", "").strip()
            
            if existing_insight:
                # If there's already an insight, add to it
                player_data["insights"] = f"{existing_insight}\n\n{insight_text}"
            else:
                player_data["insights"] = insight_text
            
            updated_players.append(player_data["name"])
        else:
            # Add to unmatched insights
            unmatched_insights.append({
                "player_name": player_name,
                "insight": insight_text
            })
    
    # Save updated JSON
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(tournament_data, f, indent=2)
    
    return {
        "updated": updated_players,
        "unmatched_insights": unmatched_insights
    }

def main():
    parser = argparse.ArgumentParser(description="Extract player insights from transcripts using Claude API")
    parser.add_argument("--transcript", required=True, help="Path to transcript file")
    parser.add_argument("--json_file", required=True, help="Path to tournament JSON file")
    parser.add_argument("--event_name", required=True, help="Name of the golf event")
    parser.add_argument("--api_key", help="Claude API key (or set ANTHROPIC_API_KEY env variable)")
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
            # Ensure we're writing a string, not a list or other object
            if isinstance(claude_response, list):
                f.write("\n".join([str(item) for item in claude_response]))
            else:
                f.write(str(claude_response))
        print(f"Raw Claude response saved to {output_path}")
    
    # Parse response
    insights = parse_claude_response(claude_response)
    print(f"Extracted {len(insights)} player insights")
    
    # Print the extracted insights for testing/review
    print("\n=== EXTRACTED INSIGHTS ===")
    for i, insight_item in enumerate(insights, 1):
        print(f"\n{i}. Player: {insight_item['player_name']}")
        print(f"   Insight: {insight_item['insight'][:100]}..." if len(insight_item['insight']) > 100 else f"   Insight: {insight_item['insight']}")
    print("========================\n")
    
    # Update JSON file
    if insights:
        results = update_json_with_insights(insights, args.json_file)
        print(f"Updated {len(results['updated'])} players in {args.json_file}")
        
        # Save unmatched insights to a separate file
        unmatched_insights = results.get("unmatched_insights", [])
        if unmatched_insights:
            unmatched_file = save_unmatched_insights(unmatched_insights, args.event_name, args.transcript)
            print(f"Warning: {len(unmatched_insights)} players not found in database.")
            print(f"Unmatched insights saved to: {unmatched_file}")
            
            # Print the list of unmatched player names
            print("Unmatched players: " + ", ".join([item["player_name"] for item in unmatched_insights]))
            
        # Update the text file based on the updated JSON
        text_file = update_text_from_json(args.json_file)
        print(f"Updated text file: {text_file}")
    else:
        print("No insights were extracted. Check Claude's response.")

if __name__ == "__main__":
    main()