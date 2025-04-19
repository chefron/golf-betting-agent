"""
Main module for the Head Pro Twitter automation.

This script handles the scheduling and coordination of tweet generation
and posting for the Head Pro, analyzing golfers' mental states and
providing betting recommendations.

"""

import os
import json
import logging
import argparse
import datetime
from typing import List, Dict, Any, Optional
import time
import random
from pathlib import Path

from tweet_generator import HeadProTweetGenerator
from post import TwitterPoster

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("head_pro_tweets.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("head_pro.main")

class HeadProTwitterBot:
    def __init__(self):
        """
        Initialize the Head Pro Twitter bot.
        """
        self.config_file = "config.json"
        self.db_path = "data/db/mental_form.db"
        self.history_file = "twitter/tweet_history.json"
        self.persona_file = "twitter/head_pro_persona.txt"
        self.player_list_file = "twitter/player_list.json"

        # Create directories if they don't exist
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)

        # Load configuration
        self.config = self._load_config()

        # Initialize components
        self.generator = HeadProTweetGenerator(
            persona_file=self.persona_file,
            db_path=self.db_path
        )

        self.poster = TwitterPoster(
            history_file=self.history_file
        )

        # Load player list
        self.player_list = self._load_player_list()

        logger.info("Head Pro Twitter bot initialized")

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from the config file."""
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            logger.info(f"Loaded configuration from {self.config_file}")
            return config
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load config from {self.config_file}: {e}")
            logger.info("Using default configuration")

            # Default configuration
            return {
                "default_markets": ["win", "top_5", "top_10"],
                "review_mode": True,
                "tweet_interval_hours": 6,
                "random_interval_variation": 1.5,  # +/- hours of randomness
            }
        
    def _load_player_list(self) -> List[Dict[str, Any]]:
        """Load the list of players to tweet about"""
        try:
            with open(self.player_list_file, 'r') as f:
                player_list = json.load(f)
            logger.info(f"Loaded player list from {self.player_list_file} with {len(player_list)} players")
            return player_list
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load player list from {self.player_list_file}: {e}")
            logger.info("Using empty player list. Please create a player list file.")
            return []
        
    def save_player_list(self) -> None:
        """Save the player list to file."""
        try:
            with open(self.player_list_file, 'w') as f:
                json.dump(self.player_list, f, indent=2)
            logger.info(f"Saved player list to {self.player_list_file}")
        except Exception as e:
            logger.error(f"Failed to save player list: {e}")

    def update_player_list(self, new_player_list: List[Dict[str, Any]]) -> None:
        """Update the player list with new data."""
        self.player_list = new_player_list
        self.save_player_list()

    def get_next_player(self) -> Optional[Dict[str, Any]]:
        """
        Get the next player to tweet about.
        
        Players with 'priority' flag will be chosen first.
        Otherwise, players who haven't been tweeted about recently will be prioritized.
        
        Returns:
            Dictionary with player information or None if no player is available
        """
        if not self.player_list:
            logger.warning("Player list is empty")
            return None
        
        # First, look for priority players who haven't been tweeted
        priority_players = [p for p in self.player_list if p.get('priority') and not p.get('tweeted')]
        
        if priority_players:
            logger.info(f"Found {len(priority_players)} priority players to tweet about")
            return random.choice(priority_players)
        
        # Next, look for any players who haven't been tweeted yet
        untweeted_players = [p for p in self.player_list if not p.get('tweeted')]
        
        if untweeted_players:
            logger.info(f"Found {len(untweeted_players)} untweeted players")
            return random.choice(untweeted_players)
        
        # If all players have been tweeted about, don't reset - just notify and return None
        logger.info("All players have been tweeted about. No more players available to tweet about.")
        return None
    
    def mark_player_as_tweeted(self, player_id: int) -> None:
        """
        Mark a player as having been tweeted about.

        Args:
            player_id: The database ID of the player
        """
        for player in self.player_list:
            if player.get('id') == player_id:
                player['tweeted'] = True
                player['last_tweeted'] = datetime.datetime.now().isoformat()
                break
        
        self.save_player_list()

    def generate_and_post_tweet(self, review: bool = None) -> Optional[Dict[str, Any]]:
        """
        Generate and post a tweet about the next player in the list.

        Args:
            review: Whether to request manual review before posting.
            If None, the value from the config is used.

        Returns:
            Result dictionary from posting attempt or None if no tweet was posted 
        """
        # Determine whether review is needed
        review_needed = review if review is not None else self.config.get("review_mode", True)

        # Get the next player to tweet about
        player = self.get_next_player()

        if not player:
            logger.warning("No player available to tweet about")
            return None
        
        player_id = player.get('id')
        markets = player.get('markets') or self.config.get('default_markets')
        tournament = player.get('tournament') or None

        logger.info(f"Generating tweet for player ID {player_id} about markets {markets}")

        try:
            # Generate tweet
            tweet_text, context = self.generator.generate_tweet(
                player_id=player_id,
                markets=markets,
                tournament_name=tournament
            )

            logger.info(f"Generate tweet ({len(tweet_text)} chars)")

            if review_needed:
                # Display the tweet for review
                print("\n" + "="*50)
                print("TWEET PREVIEW:")
                print("-"*50)
                print(tweet_text)
                print("-"*50)
                print(f"Length: {len(tweet_text)}/280 characters")
                print("="*50)

                # Get user input for approval
                approval = input("Post this tweet? (y/n/edit): ").strip().lower()

                if approval == 'y':
                    # Proceed with posting
                    logger.info("Tweet approved for posting")
                elif approval == 'edit':
                    # Allow manual editing
                    print("\nEnter your edited tweet below (leave empty to cancel):")
                    edited_tweet = input("> ")

                    if edited_tweet.strip():
                        tweet_text = edited_tweet
                        logger.info(f"Tweet edited manually (new length: {len(tweet_text)} chars)")
                    else:
                        logger.info("Tweet editing cancelled")
                        return None
                else:
                    # Cancel posting
                    logger.info("Tweet rejected, not posting")
                    return None
            
            # Post the tweet
            dry_run = self.config.get("dry_run", False)
            result = self.poster.post_tweet(
                content=tweet_text,
                context=context,
                dry_run=dry_run
            )

            # If posting was successful or simulated, mark the player as tweeted
            if result.get("status") in ["success", "simulated"]:
                self.mark_player_as_tweeted(player_id)
            
            return result
        
        except Exception as e:
            logger.error(f"Error generating or posting tweet: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
        
    def run_scheduled(self, duration_hours: Optional[float] = None) -> None:
        """
        Run the bot on a schedule for a specified duration.
        
        Args:
            duration_hours: How many hours to run (None for indefinite)
        """
        start_time = datetime.datetime.now()
        end_time = (start_time + datetime.timedelta(hours=duration_hours)) if duration_hours else None
        
        tweet_interval = self.config.get("tweet_interval_hours", 4)
        interval_variation = self.config.get("random_interval_variation", 1.2)
        
        logger.info(f"Starting scheduled Twitter bot. Will run{'for ' + str(duration_hours) + ' hours' if duration_hours else ' indefinitely'}.")
        logger.info(f"Tweet interval: {tweet_interval} hours (±{interval_variation} hours random variation)")
        
        try:
            while True:
                now = datetime.datetime.now()
                
                # Check if we've reached the end time
                if end_time and now >= end_time:
                    logger.info(f"Reached specified duration of {duration_hours} hours. Stopping.")
                    break
                
                # Generate and post a tweet
                result = self.generate_and_post_tweet()
                
                if result and result.get("status") in ["success", "simulated"]:
                    logger.info(f"Tweet posted successfully")
                
                # Calculate next tweet time with random variation
                variation_hours = random.uniform(-interval_variation, interval_variation)
                next_interval_hours = tweet_interval + variation_hours
                next_interval_seconds = int(next_interval_hours * 3600)
                
                next_tweet_time = now + datetime.timedelta(seconds=next_interval_seconds)
                
                logger.info(f"Next tweet scheduled for {next_tweet_time.strftime('%Y-%m-%d %H:%M:%S')} " +
                        f"({next_interval_hours:.2f} hours from now)")
                
                # Sleep until next tweet time
                time.sleep(next_interval_seconds)
                
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received. Shutting down gracefully.")
        except Exception as e:
            logger.error(f"Unexpected error in scheduler: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
        logger.info("Scheduler stopped")

def setup_player_list(bot: HeadProTwitterBot) -> None:
    """
    Interactive function to set up or update the player list.
    
    Args:
        bot: HeadProTwitterBot instance
    """
    print("\n==== Player List Setup ====")

    # Check if there's an existing list
    if bot.player_list:
        print(f"Found existing player list with {len(bot.player_list)} players.")
        action = input("What would you like to do? (view/add/remove/clear/quit): ").strip()
    else:
        print("No existing player list found.")
        action = input("What would you like to do? (add/quit): ").strip().lower()

    if action == "view":
        # Display existing players on list
        print("\nCurrent players:")
        for i, player in enumerate(bot.player_list):
            priority = "🌟 " if player.get("priority") else "   "
            tweeted = "✓" if player.get("tweeted") else " "
            markets = ", ".join(player.get("markets", []))
            print(f"{i+1}. {priority}{player.get('name')} [ID: {player.get('id')}] [{tweeted}] Markets: {markets}")

        print("\n")
        setup_player_list(bot)

    elif action == "add":
        # Add a new player
        try:
            player_name_input = input("Enter player name (or part of name): ")
            
            # Search for matching players in the database
            import sqlite3
            conn = sqlite3.connect(bot.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Use LIKE with wildcards for a fuzzy search
            cursor.execute("SELECT id, name FROM players WHERE LOWER(name) LIKE LOWER(?)", (f"%{player_name_input}%",))
            matching_players = cursor.fetchall()
            
            if not matching_players:
                print(f"No players found matching '{player_name_input}'")
                conn.close()
                setup_player_list(bot)  # Return to menu
                return
                
            # If multiple matches, let user choose
            if len(matching_players) > 1:
                print("\nMultiple matching players found:")
                for i, p in enumerate(matching_players):
                    print(f"{i+1}. {p['name']} (ID: {p['id']})")
                    
                selection = input("\nEnter number of player to add (or 'c' to cancel): ")
                
                if selection.lower() == 'c':
                    conn.close()
                    setup_player_list(bot)  # Return to menu
                    return
                    
                try:
                    index = int(selection) - 1
                    if 0 <= index < len(matching_players):
                        player_id = matching_players[index]['id']
                        player_name = matching_players[index]['name']
                    else:
                        print("Invalid selection.")
                        conn.close()
                        setup_player_list(bot)  # Return to menu
                        return
                except ValueError:
                    print("Invalid input. Please enter a number.")
                    conn.close()
                    setup_player_list(bot)  # Return to menu
                    return
            else:
                # Single match found
                player_id = matching_players[0]['id']
                player_name = matching_players[0]['name']
                
            conn.close()
            print(f"Selected player: {player_name}")

            # Get markets to analyze
            default_markets = bot.config.get("default_markets", ["win", "top_5", "top_10", "top_20"])
            markets_input = input(f"Enter markets to analyze (comma-separated, leave empty for defaults {default_markets}): ")

            if markets_input.strip():
                markets = [m.strip() for m in markets_input.split(",")]
            else:
                markets = default_markets

            # Check if this is a priority player
            priority = input("Is this a priority player? (y/n): ").strip().lower() == "y"

            # Create player entry
            player = {
                "id": player_id,
                "name": player_name,
                "markets": markets,
                "priority": priority,
                "tweeted": False
            }

            # Add tournament if specified
            tournament = input("Tournament name (leave empty for current): ").strip()
            if tournament:
                player["tournament"] = tournament

            # Add to player list
            bot.player_list.append(player)
            bot.save_player_list()

            print(f"Added player: {player_name} with markets: {markets}")

            # Ask if they want to add another player
            if input ("Add another player? (y/n): ").strip().lower() == "y":
                setup_player_list(bot)

        except Exception as e:
            print(f"Error adding player: {e}")
            setup_player_list(bot)

    elif action == "remove":
        if not bot.player_list:
            print("No players to remove.")
            setup_player_list(bot)
            return
        
        # Remove a player
        try:
            print("\nCurrent players:")
            for i, player in enumerate(bot.player_list):
                print(f"{i+1}. {player.get('name')} [ID: {player.get('id')}]")

            selection = input("Enter number of player to remove (or 'c' to cancel): ")

            if selection.lower() == 'c':
                setup_player_list(bot)
                return
            
            index = int(selection) - 1
            if 0 <= index < len(bot.player_list):
                removed = bot.player_list.pop(index)
                bot.save_player_list()
                print(f"Removed player: {removed.get('name')}")
            else:
                print("Invalid selection.")
                
            setup_player_list(bot)
            
        except Exception as e:
            print(f"Error removing player: {e}")
            setup_player_list(bot)

    elif action == "clear":
        # Clear the list
        confirm = input("Are you sure you want to clear the entire player list? (yes/no): ").strip().lower()

        if confirm == "yes":
            bot.player_list = []
            bot.save_player_list()
            print("Player list cleared.")
        else:
            print("Clear operation cancelled.")

        setup_player_list(bot)
    
    elif action == "quit":
        print("Exiting player list setup.")

    else:
        print("Invalid action.")
        setup_player_list(bot)

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Run the Head Pro Twitter bot")
    parser.add_argument("--setup", action="store_true", help="Set up the player list interactively")
    parser.add_argument("--tweet-now", action="store_true", help="Generate and post a tweet immediately")
    parser.add_argument("--run", action="store_true", help="Run the scheduler")
    parser.add_argument("--duration", type=float, default=None, help="Duration to run in hours (default: indefinitely)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate tweeting without actually posting")

    args = parser.parse_args()

    bot = HeadProTwitterBot()

    # Update config with dry run flag if specified
    if args.dry_run:
        bot.config["dry_run"] = True
        logger.info("Dry run mode enabled")

    # Handle actions
    if args.setup:
        setup_player_list(bot)
    elif args.tweet_now:
        result = bot.generate_and_post_tweet()
        if result:
            print(f"Tweet posted with status: {result.get('status')}")
        else:
            print("Failed to generate or post tweet")
    elif args.run:
        bot.run_scheduled(duration_hours=args.duration)
    else:
        # No action specified, show help
        parser.print_help()

if __name__ == "__main__":
    main()













                        
                    

                    






        
                        
                        
                        