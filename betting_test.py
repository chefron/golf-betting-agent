#!/usr/bin/env python3
"""
Test script for the GolfBettingTracker's identify_recommended_bets method.
This script creates an instance of the betting tracker and runs the method
to verify it correctly identifies recommended betting opportunities.
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Ensure the API key is set
if not os.getenv('DATAGOLF_API_KEY'):
    print("Warning: DATAGOLF_API_KEY environment variable not set.")
    print("Using default API key from odds_retriever.py")

# Add the parent directory to the path if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the GolfBettingTracker
from betting_tracker import GolfBettingTracker

def test_identify_recommended_bets():
    """Test the identify_recommended_bets method"""
    print("Initializing GolfBettingTracker...")
    # Get API key from environment variable or use default
    api_key = os.getenv('DATAGOLF_API_KEY', "6e301f31eb610c59de6fa2e57009")
    
    # Define which sportsbook to use (e.g., "draftkings", "fanduel", "betmgm")
    target_sportsbook = "bovada"
    
    # Create an instance of the betting tracker with a default sportsbook
    tracker = GolfBettingTracker(api_key, default_sportsbook=target_sportsbook)
    
    print(f"\nTesting identify_recommended_bets method for {target_sportsbook.upper()}...")
    print("This will fetch live odds data and identify value bets\n")
    
    # Set parameters for the test
    min_ev = 7.0          # Minimum EV threshold (%)
    bankroll = 1000       # Example bankroll
    min_stake = 1.0       # Minimum stake to recommend
    max_recommendations = 50  # Number of recommendations to show

    # Add this before calling identify_recommended_bets
    from odds_retriever import OddsRetriever
    debug_retriever = OddsRetriever(db_path="data/db/mental_form.db")
    debug_data = debug_retriever.update_odds_data()

    # Debug specific players from the target sportsbook
    print(f"\nDebug: Checking for specific players on {target_sportsbook.upper()}...")
    for market_name, market_data in debug_data.get("markets", {}).items():
        if market_name == "win":  # Only check win market
            for player in market_data:
                if "Mullinax" in player.get("player_name", ""):
                    print(f"Found Mullinax in win market:")
                    
                    # Check sportsbooks data
                    for book in player.get("sportsbooks", []):
                        # Only show the target sportsbook
                        if book['name'].lower() == target_sportsbook.lower():
                            print(f"  {book['name']}: odds={book.get('american_odds')}, base_ev={book.get('base_ev'):.2f}%, adj_ev={book.get('adjusted_ev'):.2f}%")
    
    # Run the method and capture results
    try:
        results = tracker.identify_recommended_bets(
            min_ev=min_ev,
            bankroll=bankroll,
            min_stake=min_stake,
            max_recommendations=max_recommendations
        )
        
        # Print the results in a formatted way
        print("\n" + "="*80)
        print(f"TEST RESULTS: {len(results['recommendations'])} recommendations found for {target_sportsbook.upper()}")
        print(f"Event: {results['event_name']}")
        print(f"Identified at: {results['identified_at']}")
        print(f"Total opportunities: {results['total_opportunities']}")
        print("="*80)
        
        # Show detailed recommendations
        if results['recommendations']:
            print("\nDetailed Recommendations:")
            print("-"*80)
            for i, rec in enumerate(results['recommendations']):
                print(f"#{i+1}: {rec['player_name']} - {rec['market']}")
                print(f"  Sportsbook: {rec['sportsbook']} | Odds: {rec['american_odds']}")
                print(f"  Base EV: {rec['base_ev']:.2f}% | Mental Adjustment: {rec['mental_adjustment']:.2f}%")
                print(f"  Adjusted EV: {rec['adjusted_ev']:.2f}%")
                print(f"  Mental Score: {rec['mental_form_score'] if rec['mental_form_score'] is not None else 'N/A'}")
                print(f"  Recommended Stake: ${rec['kelly_stake']:.2f} ({rec['kelly_percentage']:.2f}% of bankroll)")
                print("-"*80)
        else:
            print(f"\nNo betting recommendations found for {target_sportsbook.upper()} that meet the criteria.")
            
        return True
        
    except Exception as e:
        print(f"Error testing identify_recommended_bets: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Close the database connection
        tracker.close()

if __name__ == "__main__":
    print(f"Running test at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    success = test_identify_recommended_bets()
    print(f"\nTest {'completed successfully' if success else 'failed'}")