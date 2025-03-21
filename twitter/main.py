#!/usr/bin/env python3
"""
Main script to generate and post tweets for Fat Phil.

This script uses a dynamic approach to find the most relevant betting markets
based on player insights, fetches targeted odds data, and generates
specialized tweets focused on the most valuable betting angles.

Usage:
  python main.py --database=path/to/tournament_database.json [--dry-run]

Options:
  --database    Path to the tournament database JSON file
  --dry-run     Generate but don't post the tweet
"""

import os
import sys
import argparse
import logging
from post import TwitterPost
from tweet_generator import TweetGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('fat_phil_tweets.log')
    ]
)
logger = logging.getLogger('fat_phil')

def main():
    """Run the tweet generation and posting process."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Generate and post tweets for Fat Phil')
    parser.add_argument('--database', required=True, help='Path to tournament database JSON file')
    parser.add_argument('--dry-run', action='store_true', help='Generate but don\'t post the tweet')
    
    args = parser.parse_args()
    
    try:
        # Create tweet history file path
        history_file = os.path.join(os.path.dirname(__file__), 'tweet_history.json')
        
        # Initialize Twitter poster
        twitter = TwitterPost(
            username="FatPhilGolf",  # Replace with your actual Twitter username
            history_file=history_file
        )
        
        # Get recent tweets to avoid repetition
        recent_tweets = twitter.get_recent_tweets(5)
        
        # Initialize tweet generator
        generator = TweetGenerator()
        
        # Generate a tweet based on database insights with dynamic market analysis
        tweet_text = generator.generate_tweet(args.database, recent_tweets)
        
        # Display generated tweet
        print("\n" + "="*60)
        print("GENERATED TWEET:")
        print(tweet_text)
        print("="*60 + "\n")
        
        # Post the tweet if not in dry run mode
        if not args.dry_run:
            response = twitter.post_tweet(tweet_text)
            tweet_id = response.get('data', {}).get('id')
            logger.info(f"Tweet posted successfully with ID: {tweet_id}")
            print(f"Tweet posted successfully: https://twitter.com/FatPhilGolf/status/{tweet_id}")
        else:
            logger.info("Dry run mode - tweet was not posted")
            print("Dry run mode - tweet was not posted")
        
        return 0
        
    except Exception as e:
        logger.error(f"Error: {e}")
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())