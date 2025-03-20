import json
import argparse

def update_text_from_json(json_file, insights_only=True):
    """
    Create/update text file based on lightweight JSON database
    
    Args:
        json_file (str): Path to the JSON file
        insights_only (bool): If True, only include players with insights
    """
    # Load JSON data
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Generate text content
    db_text = f"TOURNAMENT: {data['tournament']['name']}, {data['tournament']['date']}\n"
    db_text += f"LAST UPDATED: {data['tournament']['last_updated']}\n\n"
    db_text += "PLAYERS:\n\n"
    
    # Collect players, filtering for those with insights if requested
    players_to_include = []
    for pid, player_data in data["players"].items():
        # Skip players without insights if insights_only is True
        if insights_only and (not player_data.get("insights") or player_data.get("insights").strip() == ""):
            continue
        
        players_to_include.append((pid, player_data))
    
    # If we're filtering for insights only, mention how many players were included vs total
    if insights_only:
        total_players = len(data["players"])
        insights_players = len(players_to_include)
        db_text += f"[Showing {insights_players} players with insights out of {total_players} total players]\n\n"
    
    # Add each player's information
    for pid, player_data in players_to_include:
        # Add player name
        db_text += f"**{player_data['name']}**\n"
        
        # Add insights
        insights_text = player_data.get('insights', '[None recorded yet]')
        db_text += f"- **Insights**: {insights_text}\n\n"
    
    # Save to text file
    text_file = json_file.replace('.json', '.txt')
    if insights_only:
        # Create a separate file for insights-only version
        text_file = json_file.replace('.json', '_insights_only.txt')
    
    with open(text_file, 'w', encoding='utf-8') as f:
        f.write(db_text)
    
    print(f"Updated text file: {text_file}")
    return text_file

def main():
    parser = argparse.ArgumentParser(description="Update text file from lightweight JSON database")
    parser.add_argument("--json_file", required=True, help="Path to tournament JSON file")
    parser.add_argument("--all_players", action="store_true", help="Include all players, not just those with insights")
    
    args = parser.parse_args()
    update_text_from_json(args.json_file, insights_only=not args.all_players)

if __name__ == "__main__":
    main()