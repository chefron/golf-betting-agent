import requests
import json
from datetime import datetime
import os

def fetch_datagolf_api(endpoint, params=None):
    """Fetch data from the DataGolf API"""
    if params is None:
        params = {}
    
    # Add API key to params
    params['key'] = "6e301f31eb610c59de6fa2e57009"
    
    # Build base URL
    base_url = "https://feeds.datagolf.com"
    url = f"{base_url}/{endpoint}"
    
    print(f"Fetching: {url}")
    
    # Make the request
    response = requests.get(url, params=params)
    
    # Check for errors
    response.raise_for_status()
    
    # Return JSON data
    return response.json()

def calculate_ev(dg_probability, decimal_odds):
    """Calculate Expected Value (EV) percentage"""
    # Convert percentage to decimal
    prob = dg_probability / 100
    
    # Calculate EV
    ev = (prob * (decimal_odds - 1)) - (1 - prob)
    
    # Convert to percentage
    ev_pct = ev * 100
    
    return ev_pct

def format_player_to_text(player_data, markets=["win", "top_5", "top_10", "top_20"]):
    """Format a single player's data for text output with improved formatting and consolidated sportsbooks"""
    text = f"**{player_data['name']}**\n"
    
    # Add market data
    for market in markets:
        if market in player_data["markets"] and player_data["markets"][market]["sportsbooks"]:
            # Format market name to be more readable (e.g., "top_5" -> "Top 5")
            market_display = market.replace('_', ' ').title()
            text += f"- {market_display}:\n"
            
            # Calculate decimal odds from probability (prob = 100/decimal)
            probability = player_data["markets"][market]["dg_probability"]
            model_decimal = 100 / probability if probability > 0 else 0
            
            # Format with both decimal and percentage
            text += f"  - The model: {model_decimal:.2f} ({probability:.1f}%)\n"
            
            # Sort sportsbooks by EV
            sportsbooks = []
            for book, book_data in player_data["markets"][market]["sportsbooks"].items():
                sportsbooks.append((book, book_data))
            
            sportsbooks.sort(key=lambda x: x[1]["ev"], reverse=True)
            
            # Consolidate all sportsbooks into a single line
            books_text = []
            for book, book_data in sportsbooks:
                # Special handling for sportsbook capitalization
                if book.lower() == "betmgm":
                    book_display = "BetMGM"
                elif book.lower() == "draftkings":
                    book_display = "DraftKings"
                elif book.lower() == "fanduel":
                    book_display = "FanDuel"
                elif book.lower() == "bet365":
                    book_display = "Bet365"
                else:
                    book_display = book.capitalize()
                
                ev_sign = "+" if book_data["ev"] >= 0 else ""
                books_text.append(f"{book_display}: {book_data['odds']:.2f} ({ev_sign}{book_data['ev']:.1f}%)")
            
            text += f"  - {' | '.join(books_text)}\n"
    
    # Add insights ONLY if they exist and aren't empty
    insights = player_data.get('insights', '')
    if insights and insights.strip():  # Check if insights is not empty or just whitespace
        text += f"- **Insights**: {insights}\n"
    
    text += "\n"  # Add blank line at the end regardless
    
    return text

def build_tournament_database():
    """Build a concise tournament database from the outrights endpoint"""
    try:
        # The sportsbooks we want to track
        target_sportsbooks = ['bet365', 'betmgm', 'bovada', 'caesars', 'draftkings', 'fanduel', 'pinnacle']
        
        # Markets to fetch
        markets = ["win", "top_5", "top_10", "top_20"]
        
        # Fetch data for each market
        market_data = {}
        for market in markets:
            market_data[market] = fetch_datagolf_api("betting-tools/outrights", {
                "tour": "pga",
                "market": market,
                "odds_format": "decimal"
            })
            print(f"Fetched {market} market data")
            
        # Get tournament info from the first market response
        tournament_name = market_data["win"]["event_name"]
        last_updated = market_data["win"]["last_updated"]
        print(f"Building database for {tournament_name}")
        
        # Track players and their odds
        players = {}
        
        # Process each market
        for market, data in market_data.items():
            # Process odds for each player
            for player_odds in data["odds"]:
                player_id = player_odds["dg_id"]
                player_name = player_odds["player_name"]
                
                # Add player to our tracker if not already there
                if player_id not in players:
                    players[player_id] = {
                        "id": player_id,
                        "name": player_name,
                        "markets": {},
                        "insights": ""  # Empty insights field to start
                    }
                
                # Extract DataGolf model odds
                dg_probability = 0
                if "datagolf" in player_odds:
                    # Check which model to use (prefer baseline_history_fit if available)
                    if player_odds["datagolf"].get("baseline_history_fit"):
                        dg_model_odds = player_odds["datagolf"]["baseline_history_fit"]
                        dg_probability = 100 / dg_model_odds if dg_model_odds > 0 else 0
                        model_used = "baseline_history_fit"
                    elif player_odds["datagolf"].get("baseline"):
                        dg_model_odds = player_odds["datagolf"]["baseline"]
                        dg_probability = 100 / dg_model_odds if dg_model_odds > 0 else 0
                        model_used = "baseline"
                    else:
                        model_used = "unknown"
                else:
                    model_used = "none"
                
                # Initialize market data
                players[player_id]["markets"][market] = {
                    "dg_probability": dg_probability,
                    "dg_model": model_used,
                    "sportsbooks": {}
                }
                
                # Add odds for each target sportsbook
                for book in target_sportsbooks:
                    if book in player_odds and player_odds[book] is not None and player_odds[book] > 0:
                        decimal_odds = player_odds[book]
                        ev = calculate_ev(dg_probability, decimal_odds)
                        
                        players[player_id]["markets"][market]["sportsbooks"][book] = {
                            "odds": decimal_odds,
                            "ev": ev
                        }
        
        # Sort players by their "win" market DG probability (highest to lowest)
        sorted_players = []
        for player_id, player_data in players.items():
            # Only include players with odds in the "win" market
            if "win" in player_data["markets"]:
                win_probability = player_data["markets"]["win"]["dg_probability"]
                sorted_players.append((player_id, player_data, win_probability))
        
        # Sort by win probability descending
        sorted_players.sort(key=lambda x: x[2], reverse=True)
        
        # Build the database text
        current_date = datetime.now().strftime("%Y-%m-%d")
        db_text = f"TOURNAMENT: {tournament_name}, {current_date}\n"
        db_text += f"LAST UPDATED: {last_updated}\n\n"
        db_text += "PLAYERS:\n\n"
        
        # Create JSON structure
        json_data = {
            "tournament": {
                "name": tournament_name,
                "date": current_date,
                "last_updated": last_updated
            },
            "players": {}
        }
        
        # Add player data to both text and JSON formats
        for player_id, player_data, _ in sorted_players:
            # Add to text format using the new formatting function
            db_text += format_player_to_text(player_data, markets)
            
            # Add to JSON format
            json_data["players"][player_id] = {
                "id": player_id,
                "name": player_data["name"],
                "markets": player_data["markets"],
                "insights": player_data.get("insights", "")
            }
        
        # Create the output directory if it doesn't exist
        os.makedirs("data", exist_ok=True)
        
        # Get a filename base from the tournament name (remove spaces and special chars)
        tournament_slug = tournament_name.lower().replace(' ', '_').replace("'", "").replace('"', '')
        
        # Write the database to text file
        text_filename = f"data/{tournament_slug}_{current_date}.txt"
        with open(text_filename, "w", encoding="utf-8") as f:
            f.write(db_text)
        
        # Write the database to JSON file
        json_filename = f"data/{tournament_slug}_{current_date}.json"
        with open(json_filename, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2)
            
        print(f"Tournament database created and saved to:")
        print(f"- Text format: {text_filename}")
        print(f"- JSON format: {json_filename}")
        
        # Return both formats
        return {
            "text": db_text,
            "json": json_data
        }
        
    except Exception as e:
        print(f"Error building tournament database: {e}")
        import traceback
        traceback.print_exc()
        return None

def update_player_insights(json_filename, player_id, insights):
    """Update insights for a specific player in the JSON database"""
    try:
        # Load existing JSON data
        with open(json_filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Update insights if player exists
        if player_id in data["players"]:
            data["players"][player_id]["insights"] = insights
            print(f"Updated insights for {data['players'][player_id]['name']}")
        else:
            print(f"Player ID {player_id} not found in database")
            return False
        
        # Save updated JSON
        with open(json_filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        # Also update the corresponding text file
        text_filename = json_filename.replace('.json', '.txt')
        if os.path.exists(text_filename):
            # Generate new text format
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
            
            # Add player data using the new formatting function
            for pid, player_data, _ in sorted_players:
                db_text += format_player_to_text(player_data)
            
            # Save updated text
            with open(text_filename, "w", encoding="utf-8") as f:
                f.write(db_text)
            
            print(f"Also updated text file: {text_filename}")
        
        return True
        
    except Exception as e:
        print(f"Error updating player insights: {e}")
        return False

def refresh_odds(json_filename):
    """Refresh odds data in an existing database file"""
    try:
        # Load existing JSON data
        with open(json_filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        print(f"Refreshing odds for {data['tournament']['name']}")
        
        # The sportsbooks we want to track
        target_sportsbooks = ['bet365', 'betmgm', 'bovada', 'caesars', 'draftkings', 'fanduel', 'pinnacle']
        
        # Markets to fetch
        markets = ["win", "top_5", "top_10", "top_20"]
        
        # Fetch data for each market
        market_data = {}
        for market in markets:
            market_data[market] = fetch_datagolf_api("betting-tools/outrights", {
                "tour": "pga",
                "market": market,
                "odds_format": "decimal"
            })
            print(f"Fetched {market} market data")
        
        # Update last updated timestamp
        data['tournament']['last_updated'] = market_data["win"]["last_updated"]
        
        # Update players data
        for market, market_response in market_data.items():
            for player_odds in market_response["odds"]:
                player_id = str(player_odds["dg_id"])  # Ensure it's a string for JSON
                
                # Skip if player not in our database
                if player_id not in data["players"]:
                    continue
                
                # Extract DataGolf model odds
                dg_probability = 0
                if "datagolf" in player_odds:
                    # Check which model to use (prefer baseline_history_fit if available)
                    if player_odds["datagolf"].get("baseline_history_fit"):
                        dg_model_odds = player_odds["datagolf"]["baseline_history_fit"]
                        dg_probability = 100 / dg_model_odds if dg_model_odds > 0 else 0
                        model_used = "baseline_history_fit"
                    elif player_odds["datagolf"].get("baseline"):
                        dg_model_odds = player_odds["datagolf"]["baseline"]
                        dg_probability = 100 / dg_model_odds if dg_model_odds > 0 else 0
                        model_used = "baseline"
                    else:
                        model_used = "unknown"
                else:
                    model_used = "none"
                
                # Initialize market data if it doesn't exist
                if market not in data["players"][player_id]["markets"]:
                    data["players"][player_id]["markets"][market] = {
                        "dg_probability": 0,
                        "dg_model": "",
                        "sportsbooks": {}
                    }
                
                # Update DataGolf probability
                data["players"][player_id]["markets"][market]["dg_probability"] = dg_probability
                data["players"][player_id]["markets"][market]["dg_model"] = model_used
                
                # Update odds for each target sportsbook
                for book in target_sportsbooks:
                    if book in player_odds and player_odds[book] is not None and player_odds[book] > 0:
                        decimal_odds = player_odds[book]
                        ev = calculate_ev(dg_probability, decimal_odds)
                        
                        data["players"][player_id]["markets"][market]["sportsbooks"][book] = {
                            "odds": decimal_odds,
                            "ev": ev
                        }
        
        # Save updated JSON
        with open(json_filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        
        # Update text file
        text_filename = json_filename.replace('.json', '.txt')
        if os.path.exists(text_filename):
            # Generate new text format
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
            
            # Add player data using the new formatting function
            for pid, player_data, _ in sorted_players:
                db_text += format_player_to_text(player_data)
            
            # Save updated text
            with open(text_filename, "w", encoding="utf-8") as f:
                f.write(db_text)
        
        print(f"Successfully refreshed odds and updated files")
        return True
        
    except Exception as e:
        print(f"Error refreshing odds: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) == 1:
        # No arguments, build new database
        print("Building new tournament database...")
        result = build_tournament_database()
        if result:
            print("\nDatabase preview (first 1000 characters):")
            print(result["text"][:1000] + "...")
        else:
            print("Failed to create tournament database")
    
    elif sys.argv[1] == "refresh" and len(sys.argv) >= 3:
        # Refresh odds for existing database
        json_file = sys.argv[2]
        print(f"Refreshing odds for {json_file}...")
        refresh_odds(json_file)
    
    elif sys.argv[1] == "update" and len(sys.argv) >= 5:
        # Update insights for a player
        json_file = sys.argv[2]
        player_id = sys.argv[3]
        insights = sys.argv[4]
        print(f"Updating insights for player {player_id} in {json_file}...")
        update_player_insights(json_file, player_id, insights)
    
    else:
        print("Usage:")
        print("  python tournament_db.py                  # Build new tournament database")
        print("  python tournament_db.py refresh file.json  # Refresh odds in existing database")
        print("  python tournament_db.py update file.json player_id \"insights text\"  # Update player insights")