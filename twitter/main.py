#!/usr/bin/env python3
"""
Main script to generate and post tweets for Fat Phil.

Usage:
  python main.py --insights=path/to/insights_file.txt [--debug] [--dry-run]

Options:
  --insights    Path to the insights text file
  --debug       Enable debug mode (detailed logging)
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
    parser.add_argument('--insights', required=True, help='Path to insights text file')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--dry-run', action='store_true', help='Generate but don\'t post the tweet')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug mode enabled")
    
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
        
        # Initialize tweet generator (with debug mode if specified)
        generator = TweetGenerator(debug=args.debug)
        
        # Generate a tweet based on insights
        tweet_text = generator.generate_tweet(args.insights, recent_tweets)
        
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