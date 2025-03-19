import os
import json
import argparse
from tournament_db import format_player_to_text

def update_text_from_json(json_file):
    """Create/update text file based on JSON data, using the function from tournament_db.py"""
    # Load JSON data
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Generate text content
    db_text = f"TOURNAMENT: {data['tournament']['name']}, {data['tournament']['date']}\n"
    db_text += f"LAST UPDATED: {data['tournament']['last_updated']}\n\n"
    db_text += "PLAYERS:\n\n"
    
    # Sort players by win probability
    sorted_players = []
    for pid, player_data in data["players"].items():
        win_prob = 0
        if "win" in player_data["markets"]:
            win_prob = player_data["markets"]["win"]["dg_probability"]
        sorted_players.append((pid, player_data, win_prob))
    
    sorted_players.sort(key=lambda x: x[2], reverse=True)
    
    # Add player data using the formatting function
    for pid, player_data, _ in sorted_players:
        db_text += format_player_to_text(player_data)
    
    # Save to text file
    text_file = json_file.replace('.json', '.txt')
    with open(text_file, 'w', encoding='utf-8') as f:
        f.write(db_text)
    
    print(f"Updated text file: {text_file}")
    return text_file

def main():
    parser = argparse.ArgumentParser(description="Update text file from JSON database")
    parser.add_argument("--json_file", required=True, help="Path to tournament JSON file")
    
    args = parser.parse_args()
    update_text_from_json(args.json_file)

if __name__ == "__main__":
    main()