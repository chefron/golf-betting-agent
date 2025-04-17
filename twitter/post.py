"""
Twitter posting functionality for the Head Pro.

This module handles authentication and posting using the 
Twitter API v2
"""

import os
import json
import tweepy
import logging
import datetime
from typing import Dict, Optional, Any
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("head_pro_tweets.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("head_pro.twitter")

class TwitterPoster:
    def __init__(self, history_file: str = "tweet_history.json"):
        """
        Initialize the Twitter poster with API credentials.

        Args:
            history_file: Path to store tweet history
        """
        # Get API credentials from environment variables
        self.api_key = os.environ.get("TWITTER_API_KEY")
        self.api_secret = os.environ.get("TWITTER_API_SECRET")
        self.access_token = os.environ.get("TWITTER_ACCESS_TOKEN")
        self.access_secret = os.environ.get("TWITTER_ACCESS_SECRET")
        self.bearer_token = os.environ.get("TWITTER_BEARER_TOKEN")

        # Validate credentials
        missing_creds = []
        if not self.api_key:
            missing_creds.append("TWITTER_API_KEY")
        if not self.api_secret:
            missing_creds.append("TWITTER_API_SECRET")
        if not self.access_token:
            missing_creds.append("TWITTER_ACCESS_TOKEN")
        if not self.access_secret:
            missing_creds.append("TWITTER_ACCESS_SECRET")

        if missing_creds:
            logger.warning(f"Missing Twitter credentials: {', '.join(missing_creds)}")
            logger.warning("Twitter posting will be simulated but not actually performed")

        self.history_file = history_file
        self.tweet_history = self._load_history()

    def _load_history(self) -> list:
        """Load tweet history from the history file."""
        try:
            with open(self.history_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.info(f"No valid history file found at {self.history_file}. Starting fresh.")
            return []
        
    def _save_history(self) -> None:
        """Save tweet history to the history file."""
        try:
            # Create directory if it doesn't exit
            os.makedirs(os.path.dirname(os.path.abspath(self.history_file)), exist_ok=True)

            with open(self.history_file, 'w') as f:
                json.dump(self.tweet_history, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save tweet history: {e}")

    def _initialize_api(self) -> Optional[tweepy.Client]:
        """Initialize and return the Twitter API client."""
        if all([self.api_key, self.api_secret, self.access_token, self.access_secret]):
            try:
                # Initialize v2 client
                client = tweepy.Client(
                    consumer_key=self.api_key,
                    consumer_secret=self.api_secret,
                    access_token=self.access_token,
                    access_token_secret=self.access_secret
                )
                return client
            except Exception as e:
                logger.error(f"Failed to initialize Twitter API client: {e}")
                return None
        else:
            logger.warning("Missing credentials, Twitter API client not initialized")
            return None
        
    def post_tweet(self, content: str, context: Dict[str, Any] = None, dry_run: bool = False) -> Dict[str, Any]:
        """
        Post a tweet to Twitter.

        Args:
            content: The text content of the tweet
            context: Optional context information to store with the tweet history
            dry_run: If True, simulates posting but doesn't actually post

        Returns:
            Dictionary with tweet information including status and metadata
        """
        timestamp = datetime.datetime.now().isoformat()

        # Create result structure
        result = {
            "content": content,
            "timestamp": timestamp,
            "length": len(content),
            "context": context or {},
            "status": "simulated" if dry_run else "pending"
        }

        # Log the tweet
        logger.info(f"{'[DRY RUN] ' if dry_run else ''}Posting tweet ({len(content)} chars): {content}")

        if dry_run:
            result["tweet_id"] = None
            self.tweet_history.append(result)
            self._save_history()
            return result
        
        # Initialize Twitter API
        client = self._initialize_api()

        if client:
            try:
                # Post the tweet
                response = client.create_tweet(text=content)

                # Extract tweet ID from response
                tweet_id = response.data.get('id')

                logger.info(f"Tweet successfully posted with ID: {tweet_id}")

                # Update result with success information
                result["status"] = "success"
                result["tweet_id"] = tweet_id
            
            except Exception as e:
                logger.error(f"Failed to post tweet: {e}")
                result["status"] = "error"
                result["error"] = str(e)

        else:
            # API client not available
            logger.warning("Unable to post tweet: Twitter API client not available")
            result["status"] = "error"
            result["error"] = "Twitter API client not available"

        # Add to history and save
        self.tweet_history.append(result)
        self._save_history()

        return result

if __name__ == "__main__":
    # Example usage
    poster = TwitterPoster()
    test_tweet = "This is a test tweet from The Head Pro."
    result = poster.post_tweet(test_tweet, dry_run=True)
    print(json.dumps(result, indent=2))
            