import os
from dotenv import load_dotenv

load_dotenv()

# App configuration
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
PORT = int(os.environ.get('PORT', 5001))

# API Keys
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

# Database paths
DB_PATH = os.environ.get('DB_PATH', '../data/db/mental_form.db')

# Paths
PERSONA_FILE = os.environ.get('PERSONA_FILE', '../chatbot/head_pro_persona.txt')