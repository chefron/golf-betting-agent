"""
LLM Provider interface for golf mental form analysis system.

This module provides a base class and implementations for different LLM providers
that can be used for extracting insights and calculating mental scores.
"""

from abc import ABC, abstractmethod
import os
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('golf.lmm_provider')

load_dotenv()

class LLMProvider(ABC):
    """Base class for LLM providers"""

    def __init__(self, api_key=None):
        """Initialize the LLM provider with an API key"""
        self.api_key = api_key

    @abstractmethod
    def extract_insights(self, prompt):
        """
        Extract insights using the LLM.

        Args:
            prompt: The prompt sent to the LLM

        Returns:
            The LLM's response text
        """
        pass

    @abstractmethod
    def calculate_mental_form(self, prompt):
        """
        Calculate mental form using the LLM.

        Args:
            prompt: The prompt sent to the LLM

        Returns:
            The LLM's response text
        """
        pass


class AnthropicProvider(LLMProvider):
    """Claude/Anthropic API implementation"""

    def __init__(self, api_key=None):
        """Initialize the Anthropic provider"""
        super().__init__(api_key)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

        if not self.api_key:
            logger.warning("No Anthropic API key provided")

        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.api_key)
            self.available = True
        except ImportError:
            logger.error("Anthropic SDK not installed. Run: poetry add anthropic")
            self.available = False
        except Exception as e:
            logger.error(f"Error initializing Anthropic client: {e}")
            self.available = False

    def extract_insights(self, prompt):
        """Extract insights using Claude"""
        if not self.available:
            return "Error: Anthropic client not available"
        
        try:
            message = self.client.messages.create(
                model="claude-3-7-sonnet-20250219",
                max_tokens=4000,
                temperature=0,
                system="You extract precise, structured insights about professional golfers from podcast and interview transcripts.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return message.content[0].text
        except Exception as e:
            logger.error(f"Error calling Anthropic API: {e}")
            return f"Error calling Anthropic API: {str(e)}"
        
    def calculate_mental_form(self, prompt):
        """Calculate mental form score using Claude"""
        if not self.available:
            return "Error: Anthropic client not available"
        
        try:
            message = self.client.messages.create(
                model="claude-3-7-sonnet-20250219",
                max_tokens=1000,
                temperature=0.3,
                system="You are an expert in qualitative golf analysis, specializing in identifying the non-statistical factors that influence player performance. Your task is to evaluate insights about golfers and determine how the qualitative factors mentioned might cause a player to perform differently than pure statistics would predict.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return message.content[0].text
        except Exception as e:
            logger.error(f"Error calling Anthropic API: {e}")
            return f"Error calling Anthropic API: {str(e)}"

class GoogleGeminiProvider(LLMProvider):
    """Google Gemini implementation"""
    
    def __init__(self, api_key=None):
        """Initialize the Google Gemini provider"""
        super().__init__(api_key)
        # Use the provided key or get from environment
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        
        if not self.api_key:
            logger.warning("No Google API key provided")
        
        try:
            from google import genai
            genai.configure(api_key=self.api_key)
            self.genai = genai
            self.available = True
        except ImportError:
            logger.error("Google Generative AI SDK not installed. Run: pip install google-genai")
            self.available = False
        except Exception as e:
            logger.error(f"Error initializing Google Gemini client: {e}")
            self.available = False
    
    def extract_insights(self, prompt):
        """Extract insights using Gemini"""
        if not self.available:
            return "Error: Google Gemini client not available"
        
        try:
            from google.genai import types
            
            client = self.genai.Client()
            
            response = client.models.generate_content(
                model="gemini-2.5-pro-preview-03-25",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction="You extract precise, structured insights about professional golfers from podcast transcripts.",
                    temperature=0,
                    max_output_tokens=4000
                ),
            )
            return response.text
        except Exception as e:
            logger.error(f"Error calling Google Gemini API: {e}")
            return f"Error calling Google Gemini API: {str(e)}"
    
    def calculate_mental_form(self, prompt):
        """Calculate mental form score using Gemini"""
        if not self.available:
            return "Error: Google Gemini client not available"
        
        try:
            from google.genai import types
            
            client = self.genai.Client()
            
            response = client.models.generate_content(
                model="gemini-2.5-pro-preview-03-25",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction="You are an expert in qualitative golf analysis, specializing in identifying the non-statistical factors that influence player performance. Your task is to evaluate insights about golfers and determine how the qualitative factors mentioned might cause a player to perform differently than pure statistics would predict.",
                    temperature=0.3,
                    max_output_tokens=1000
                ),
            )
            return response.text
        except Exception as e:
            logger.error(f"Error calling Google Gemini API: {e}")
            return f"Error calling Google Gemini API: {str(e)}"
        
# Factory function to get the appropriate provider
def get_llm_provider(provider_name, api_key=None):
    """
    Get an LLM provider instance based on the provider name.
    
    Args:
        provider_name: Name of the provider (anthropic, openai, google, anyscale)
        api_key: Optional API key (if not provided, will use environment variable)
        
    Returns:
        An instance of the requested LLM provider
    """
    providers = {
        "anthropic": AnthropicProvider,
        "claude": AnthropicProvider,  # Alias
        "google": GoogleGeminiProvider,
        "gemini": GoogleGeminiProvider,  # Alias
    }
    
    provider_class = providers.get(provider_name.lower())
    if not provider_class:
        logger.error(f"Unknown provider: {provider_name}")
        raise ValueError(f"Unknown provider: {provider_name}")
    
    return provider_class(api_key)