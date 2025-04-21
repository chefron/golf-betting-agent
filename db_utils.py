"""
Database utility functions for the golf mental form analysis system.

This module provides functions for working with the mental form database,
including adding insights, calculating  scores, and querying data.
"""

import sqlite3
import datetime
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

def get_db_connection(db_path="data/db/mental_form.db"):
    """Get a connection to the database."""
    # Always use absolute path for consistency
    abs_path = "/home/chefron/CAPTCHA/golf-betting-agent/data/db/mental_form.db"
    
    print(f"Connecting to database at: {abs_path}")
    print(f"File exists: {os.path.exists(abs_path)}")
    print(f"Current directory: {os.getcwd()}")
    
    conn = sqlite3.connect(abs_path)
    conn.row_factory = sqlite3.Row  # This enables column access by name
    return conn

def add_insight(player_id, text, source, source_type, content_title="", content_url="", date=None):
    """
    Add a new insight for a player.
    
    Args:
        player_id: ID of the player in the database
        text: The insight text
        source: Source of the insight (podcast name, website, etc.)
        source_type: Type of source (podcast, article, tweet, etc.)
        content_title: Title of the content
        content_url: URL to the original content
        date: Date of the insight (defaults to current date)
        
    Returns:
        ID of the new insight
    """
    if date is None:
        date = datetime.datetime.now().strftime("%Y-%m-%d")
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO insights 
    (player_id, text, source, source_type, content_title, content_url, date)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (player_id, text, source, source_type, content_title, content_url, date))
    
    insight_id = cursor.lastrowid
    
    # Set mental_form last_updated to NULL to trigger recalculation
    cursor.execute('''
    UPDATE mental_form
    SET last_updated = NULL
    WHERE player_id = ?
    ''', (player_id,))
    
    conn.commit()
    conn.close()
    
    return insight_id

def calculate_mental_form(player_id, max_insights=50):
    """
    Calculate mental form score for a player based on their insights.
    Uses a self-review process to ensure justifications are self-contained.
    
    Args:
        player_id: ID of the player in the database
        max_insights: Maximum number of insights to use (most recent)
        
    Returns:
        Calculated mental form score, justification text
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get player name
    cursor.execute('SELECT name FROM players WHERE id = ?', (player_id,))
    player = cursor.fetchone()
    if not player:
        conn.close()
        raise ValueError(f"Player with ID {player_id} not found")
    
    player_name = player['name']
    
    # Get the most recent insights
    cursor.execute('''
    SELECT text, date, source_type
    FROM insights
    WHERE player_id = ?
    ORDER BY date DESC
    LIMIT ?
    ''', (player_id, max_insights))
    
    insights = cursor.fetchall()
    
    if not insights:
        conn.close()
        return 0, "No insights available for assessment."  # Neutral mental form if no insights
    
    # Use anthropic to calculate mental form
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("Anthropic API key is required but not found in environment variables")
    
    client = anthropic.Anthropic(api_key=api_key)

    # Get current date for context
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    # Prepare player name for prompt by converting "Last, First" to "First Last"
    def format_player_name(name):
        if ',' in name:
            last, first = name.split(',', 1)
            return f"{first.strip()} {last.strip()}"
        return name

    # Use the formatted name in your prompt
    player_display_name = format_player_name(player_name)
    
    # Prepare insights for prompt
    insights_text = "\n\n".join([
        f"Date: {i['date']}\n"
        f"Source: {i['source_type'] if i['source_type'] else 'Unknown'}\n"
        f"Insight: {i['text']}"
        for i in insights
    ])
    
    # Create the enhanced prompt with self-review process
    prompt = f"""
You are THE HEAD PRO, a brutally honest, whisky-soaked armchair sports psychologist with 30+ years of experience reading pro golfers' minds. You specialize in decoding body language, tone, coachspeak, and between-the-lines comments to evaluate a golfer's current mental form—not results, not stats, just their psychological state.  
You've got an uncanny ability to spot early mental indicators that predict performance shifts BEFORE they show up in results. You can identify players with strong mental indicators who are about to break out of a slump—or, conversely, spot the psychological red flags in currently successful players that signal an imminent decline in performance.  
Below is a collection of insights about {player_display_name}, drawn from interviews, pressers, and second-hand sources such as podcasts. Your job is to:

---

**STEP 1: Assign a mental form score between -1 and 1.**  
Use only qualitative, psychological signals. Do NOT consider performance results. Be predictive, not reactive.  
Use the scale below:

-1.00 to -0.75 → Completely rattled: Mentally imploding; yips likely; big red flags.  
-0.74 to -0.25 → Fragile headspace: Multiple signs of doubt, frustration, or defensiveness. Not mentally reliable.  
-0.24 to +0.24 → Neutral: Standard pro mindset, unclear signals, or not enough recent intel. Most players should fall here.  
+0.25 to +0.74 → Locked in: Authentic confidence, clarity under pressure, convincing poise. Not just saying the right things—*believing* them.  
+0.75 to +1.00 → In the zone: Flow state. Rare. Reserve for peak mental clarity and full trust in process.

---

**Important Reminders:**  
• Do **not** reward vague optimism. Standard pre-tournament talk (“feeling good,” “swing's in a good place,” etc.) is noise unless unusually authentic or revealing.  
• Be **suspicious** of surface-level confidence. Only award high scores for specific, credible signs of unusual clarity, poise, or resolve.  
• **Default to the neutral range (-0.24 to +0.24)** unless you have strong evidence to move the needle. Most golfers belong here.
• **Do not assign high scores based on outdated information.** Prioritize insights from the past 30 days (today is {today}).  
• **Do not overweight repeated themes.** Ten similar comments don't carry more weight than one—look for unique or revealing signals.  
• Your job is to be **predictive**, not reactive. Look for clues that contradict public perception. Spot a slump forming before it hits the scorecard. Identify a breakout brewing before it becomes obvious.

---

**STEP 2: Write a standalone justification (3-5 sentences).**  
This is the hardest part. Your summary must be fully self-contained and make sense WITHOUT reading the insights. Write as if the reader will only see your summary. Don't summarize the insights—reconstruct the psychology behind them in fresh, standalone language.
Assume the reader will only see your summary.  

To ensure that:  
• NEVER reference "the insights" or any source of information.  
• NEVER use phrases like “he said,” “he mentioned,” or “according to.”  
• NEVER use definite articles (“the”) when introducing new facts—use indefinite (“a”).  
• NEVER mention events without giving context (“that coaching change” is wrong; “a recent coaching change” is fine).  

**Tone guide:**  
Be colorful, blunt, and opinionated. Imagine a crusty old pro with a strong pour in hand, calling it like he sees it at the 19th hole. The more polarizing, the better. You're not here to echo the hype. You're here to sniff out what's really going on under the surface.

---

**STEP 3: Check your work.**  
• Would this score surprise a casual golf fan? If not, dig deeper or go sharper.  
• Are you relying too much on tone or surface-level quotes? If yes, rework.  
• If the score is outside the -0.24 to +0.24 range, is it justified by multiple, timely, and *unusual* indicators?

---

Now go do your thing, Head Pro. Here are the insights:  
{insights_text}  

**Your response must follow this format:**  
SCORE: [number between -1 and 1]  
JUSTIFICATION: [3-5 sentence self-contained analysis with no references to source material]

"""
    
    # Print the prompt for debugging
    print(f"\n==== PROMPT FOR {player_name} ====\n{prompt}\n==== END PROMPT ====\n")
    
    # Call Claude to analyze mental form
    response = client.messages.create(
        model="claude-3-7-sonnet-20250219",
        max_tokens=4000,
        temperature=0.3,
        system="You are an expert in qualitative golf analysis, specializing in identifying psychological factors that influence player performance. Always create self-contained explanations that don't require access to source material to understand.",
        messages=[{"role": "user", "content": prompt}]
    )
    
    # Extract mental form score and justification from response
    full_response = response.content[0].text.strip()
    
    # Always print the full response
    print(f"Mental form analysis for {player_name}:")
    print(f"Full response: '{full_response}'")
    
    # Try to parse score and justification
    try:
        # Extract score
        score_line = [line for line in full_response.split('\n') if line.startswith('SCORE:')]
        if score_line:
            score_text = score_line[0].replace('SCORE:', '').strip()
            mental_form_score = float(score_text)
            # Ensure score is in valid range
            mental_form_score = max(-1, min(1, mental_form_score))
        else:
            raise ValueError("Score not found in response")
            
        # Extract justification
        justification_line = [line for line in full_response.split('\n') if line.startswith('JUSTIFICATION:')]
        if justification_line:
            # Get the justification text, which might span multiple lines
            justification_start_idx = full_response.find('JUSTIFICATION:')
            justification_text = full_response[justification_start_idx:].replace('JUSTIFICATION:', '').strip()
        else:
            justification_text = "No justification provided."
        
        print(f"Parsed mental form score: {mental_form_score}")
        print(f"Justification: {justification_text}")
    except (ValueError, IndexError) as e:
        print(f"Error parsing mental form data: {e}. Using default neutral value (0).")
        mental_form_score = 0
        justification_text = "Error parsing response."
    
    # Update mental_form in database
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Check if mental_form record exists
    cursor.execute('SELECT id FROM mental_form WHERE player_id = ?', (player_id,))
    record = cursor.fetchone()
    
    if record:
        # Update existing record
        cursor.execute('''
        UPDATE mental_form
        SET score = ?, justification = ?, last_updated = ?
        WHERE player_id = ?
        ''', (mental_form_score, justification_text, now, player_id))
    else:
        # Create new record
        cursor.execute('''
        INSERT INTO mental_form (player_id, score, justification, last_updated)
        VALUES (?, ?, ?, ?)
        ''', (player_id, mental_form_score, justification_text, now))
    
    # Add to mental_form_history
    cursor.execute('''
    INSERT INTO mental_form_history (player_id, score, date, insights_count)
    VALUES (?, ?, ?, ?)
    ''', (player_id, mental_form_score, now, len(insights)))
    
    conn.commit()
    conn.close()
    
    return mental_form_score, justification_text

def search_players(filters=None, order_by=None, limit=None):
    """
    Flexible search function for players with optional filtering.
    
    Args:
        filters: Dictionary of field:value pairs to filter on
                (e.g., {'mental_form.score__gte': 0.3} for score >= 0.3)
        order_by: Field to order by, with optional '-' prefix for descending
                 (e.g., '-mental_form.score' for highest scores first)
        limit: Maximum number of results to return
        
    Returns:
        List of matching player records
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Start with base query joining players and mental_form tables
    query = """
    SELECT p.id, p.name, p.dg_id, p.amateur, p.country, m.score, m.justification, m.last_updated
    FROM players p
    LEFT JOIN mental_form m ON p.id = m.player_id
    """
    
    # Add WHERE clauses for filters
    where_clauses = []
    params = []
    
    if filters:
        for key, value in filters.items():
            # Handle operators in field names (e.g., mental_form.score__gte)
            if '__' in key:
                field, operator = key.split('__')
                if operator == 'gt':
                    where_clauses.append(f"{field} > ?")
                elif operator == 'gte':
                    where_clauses.append(f"{field} >= ?")
                elif operator == 'lt':
                    where_clauses.append(f"{field} < ?")
                elif operator == 'lte':
                    where_clauses.append(f"{field} <= ?")
                elif operator == 'like':
                    where_clauses.append(f"{field} LIKE ?")
                    value = f"%{value}%"  # Add wildcards for LIKE
                else:
                    where_clauses.append(f"{field} = ?")
            else:
                where_clauses.append(f"{key} = ?")
            
            params.append(value)
    
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    
    # Add ORDER BY
    if order_by:
        if order_by.startswith('-'):
            query += f" ORDER BY {order_by[1:]} DESC"
        else:
            query += f" ORDER BY {order_by} ASC"
    
    # Add LIMIT
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    
    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()
    
    return results