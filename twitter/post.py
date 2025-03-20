"""
Twitter posting module for golf betting insights.

This module provides functionality to post tweets to Twitter via the official API v2.
"""

import os
import json
import logging
import time
from typing import Dict, Optional
import requests
from requests_oauthlib import OAuth1
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('twitter.post')

# Load environment variables from .env file
load_dotenv()

class TwitterError(Exception):
    """Custom exception for Twitter-related errors"""
    pass

class TwitterPost:
    """Handles posting tweets using the Twitter API v2"""
    
    # Twitter API v2 endpoint for creating tweets
    CREATE_TWEET_URL = "https://api.twitter.com/2/tweets"
    
    def __init__(self, username: str = None, history_file: str = None):
        """
        Initialize with Twitter API credentials from environment variables.
        
        Args:
            username: Twitter username (used for history tracking)
            history_file: Optional path to store tweet history
        """
        # Get API credentials from environment variables
        self.api_key = os.getenv('TWITTER_API_KEY')
        self.api_secret = os.getenv('TWITTER_API_SECRET')
        self.access_token = os.getenv('TWITTER_ACCESS_TOKEN')
        self.access_secret = os.getenv('TWITTER_ACCESS_SECRET')
        
        # Check if credentials are provided
        if not all([self.api_key, self.api_secret, self.access_token, self.access_secret]):
            raise TwitterError(
                "Twitter API credentials not found. Please set TWITTER_API_KEY, "
                "TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, and TWITTER_ACCESS_SECRET "
                "in your .env file."
            )
        
        # Set up OAuth1 authentication
        self.oauth = OAuth1(
            self.api_key,
            client_secret=self.api_secret,
            resource_owner_key=self.access_token,
            resource_owner_secret=self.access_secret
        )
        
        self.username = username
        self.history_file = history_file
        self.tweet_history = []
        
        # Load tweet history if a history file is specified
        if self.history_file and os.path.exists(self.history_file):
            self._load_history()
            
        logger.info(f"Initialized TwitterPost for user: {self.username or 'Unknown'}")
    
    def _load_history(self):
        """Load tweet history from disk"""
        try:
            with open(self.history_file, 'r') as f:
                self.tweet_history = json.load(f)
            logger.info(f"Loaded {len(self.tweet_history)} previous tweets")
        except Exception as e:
            logger.error(f"Error loading tweet history: {e}")
            self.tweet_history = []
    
    def _save_history(self):
        """Save tweet history to disk"""
        if not self.history_file:
            return
            
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.tweet_history, f, indent=2)
            logger.info(f"Saved {len(self.tweet_history)} tweets to history")
        except Exception as e:
            logger.error(f"Error saving tweet history: {e}")
    
    def get_recent_tweets(self, count: int = 10) -> list:
        """
        Get most recent tweets
        
        Args:
            count: Number of tweets to retrieve
            
        Returns:
            List of recent tweet texts
        """
        return [tweet["text"] for tweet in self.tweet_history[:count]]
    
    def post_tweet(self, text: str, reply_to_id: Optional[str] = None) -> Dict:
        """
        Post a new tweet using Twitter API v2.
        
        Args:
            text: The text content of the tweet
            reply_to_id: Optional tweet ID to reply to
                
        Returns:
            Dict: Response from Twitter API
        """
        logger.info(f"Posting tweet: {text}")
        
        # Prepare the request payload
        payload = {"text": text}
        
        # Add reply information if provided
        if reply_to_id:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}
        
        try:
            # Make the API request
            response = requests.post(
                self.CREATE_TWEET_URL,
                json=payload,
                auth=self.oauth,
                headers={'Content-Type': 'application/json'}
            )
            
            # Check for successful response
            response.raise_for_status()
            result = response.json()
            
            tweet_id = result.get('data', {}).get('id')
            logger.info(f"Successfully created tweet with ID: {tweet_id}")
            
            # Add tweet to history if we're tracking it
            if self.history_file and not reply_to_id:  # Only track original tweets, not replies
                tweet_record = {
                    "text": text,
                    "id": tweet_id,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                self.tweet_history.insert(0, tweet_record)
                self._save_history()
            
            return result
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Failed to create tweet: {e}"
            
            # Try to extract more detailed error information
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg = f"Twitter API error: {error_data.get('title', 'Unknown error')} - {error_data.get('detail', '')}"
                except ValueError:
                    pass
            
            logger.error(error_msg)
            raise TwitterError(error_msg)


# Example usage (commented out)
"""
if __name__ == "__main__":
    # Example of using the TwitterPost class
    poster = TwitterPost(
        username="YourTwitterHandle",
        history_file="tweet_history.json"
    )
    
    # Post a tweet
    response = poster.post_tweet("This is a test tweet from the API!")
    print(f"Tweet posted with ID: {response['data']['id']}")
    
    # Get recent tweets
    recent = poster.get_recent_tweets(5)
    print(f"Recent tweets: {recent}")
"""