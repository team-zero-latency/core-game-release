import math

def create_matches_table(sql_conn): #creating the matches table
    sql_cursor=sql_conn.cursor()
    query="""
    CREATE TABLE IF NOT EXISTS matches (
        match_id INT AUTO_INCREMENT PRIMARY KEY,
        player_x_uid VARCHAR(50),
        player_o_uid VARCHAR(50),
        winner_uid VARCHAR(50),
        forfeit BOOLEAN DEFAULT FALSE,
        played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )"""
    sql_cursor.execute(query)
    sql_conn.commit()
    sql_cursor.close()

#returns the value of the expected win probability as given in the document
def expected_probability_calc(elo_opponent, elo_player):
    E=(1+math.pow(10,(elo_opponent-elo_player)/400))
    return E**(-1)

#returns the elo of the player using the formula 
def elo_calculator(S, elo_opponent, elo_player):
    E=expected_probability_calc(elo_opponent,elo_player)
    new_elo=elo_player+32*(S-E)
    return round(new_elo)

#this function updates the elo of both players when match ends gracefully
#in this i am assuming that user1_id is the one which has been assigned X in tic-tac-toe and user2_id is of 
# the one which got O
def update_elo_when_match_ended(sql_conn, user1_uid, user2_uid, elo1, elo2, winner):
    S1=S2=0
    if(winner==1):
        S1=1
        S2=0
        winner_id=user1_uid
    elif(winner==0):
        S1=0
        S2=1   
        winner_id=user2_uid
    else:
        S1=S2=0.5
        winner_id=None
    new_elo_1=elo_calculator(S1,elo2,elo1)
    new_elo_2=elo_calculator(S2,elo1,elo2)
    
    sql_cursor=sql_conn.cursor()
    sql_query="UPDATE users SET elo_rating = %s WHERE uid = %s"
    sql_cursor.execute(sql_query,(new_elo_1,user1_uid))
    sql_conn.commit()
    sql_cursor.execute(sql_query,(new_elo_2,user2_uid))
    sql_conn.commit()
    match_query = "INSERT INTO matches (player_x_uid, player_o_uid, winner_uid, forfeit) VALUES (%s, %s, %s, FALSE)"
    sql_cursor.execute(match_query, (user1_uid, user2_uid, winner_id))
    sql_conn.commit()
    sql_cursor.close()
    return new_elo_1, new_elo_2

#this function updates the elo of the player in the case of a ragequit
def update_elo_when_ragequit(sql_conn, player_x_uid, player_o_uid, forfeiter_id, elo_x, elo_o):
    if forfeiter_id == player_x_uid:
        S_x = 0
        S_o = 1
        winner_uid = player_o_uid
    else:
        S_x = 1
        S_o = 0
        winner_uid = player_x_uid
    new_elo_x=elo_calculator(S_x,elo_o,elo_x)
    new_elo_o=elo_calculator(S_o,elo_x,elo_o)
    sql_cursor=sql_conn.cursor()
    sql_query="UPDATE users SET elo_rating = %s WHERE uid = %s"
    sql_cursor.execute(sql_query,(new_elo_x,player_x_uid))
    sql_cursor.execute(sql_query,(new_elo_o,player_o_uid))
    match_query = "INSERT INTO matches (player_x_uid, player_o_uid, winner_uid, forfeit) VALUES (%s, %s, %s, TRUE)"
    sql_cursor.execute(match_query, (player_x_uid, player_o_uid, winner_uid))
    sql_conn.commit() 
    sql_cursor.close()
    return new_elo_x, new_elo_o