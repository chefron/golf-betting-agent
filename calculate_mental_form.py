from db_utils import calculate_mental_form, get_db_connection

# Connect to the database
conn = get_db_connection()
cursor = conn.cursor()

# Get players with insights
cursor.execute('''
SELECT DISTINCT p.id, p.name 
FROM players p
JOIN insights i ON p.id = i.player_id
''')
players_with_insights = cursor.fetchall()

# Calculate mental form for each player
for player in players_with_insights:
    player_id = player['id']
    player_name = player['name']
    
    score, justification = calculate_mental_form(player_id)

conn.close()