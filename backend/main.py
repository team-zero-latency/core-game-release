from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from pymongo import MongoClient
import mysql.connector
from utils.facial_recognition_module import build_encodings_cache, find_closest_match
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import secrets
import elo #importing the python file which calculates the new elos
import os
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import pooling
import time
import uuid
from datetime import datetime

load_dotenv()

#create the fastapi instance                                                                                                    
app = FastAPI()

#add CORS middleware to allow requests from the frontend
app.add_middleware(CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:3000",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#connect to mongodb
mongo_client = MongoClient(os.getenv("MONGO_URI"), serverSelectionTimeoutMS=2000)
mongo_client.server_info() 
mongo_db = mongo_client["arena_db"]

#connect to mysql
db_pool=pooling.MySQLConnectionPool(
    pool_name="arena_pool",
    pool_size=10,
    pool_reset_session=True,
    host=os.getenv("MYSQL_HOST", "localhost"),
    user=os.getenv("MYSQL_USER"),
    password=os.getenv("MYSQL_PASSWORD"),
    database="arena_db",
    autocommit=True
)
conn = db_pool.get_connection()
elo.create_matches_table(conn)

#reset all users to offline on backend startup
with conn.cursor() as startup_cursor:
    startup_cursor.execute("UPDATE users SET is_online = FALSE")
    conn.commit()

#dict to store active sessions with key as session_id and value as dict of user uid, name, elo
active_sessions = {}

#cursor that returns dictionaries since we want to access columns by name
sql_cursor=conn.cursor(dictionary=True)

#fetch all profile images from mongodb and create a dictionary of uid to image data
images_collection = mongo_db["profile_images"]
print("loading images from mongodb")
db_images_dict = {img["uid"]: img["image_data"] for img in images_collection.find()}
print("images loaded:", len(db_images_dict))
#build the encodings cache using the facial recognition module
print("building encodings cache")
encodings_cache = build_encodings_cache(db_images_dict)
print("encodings cache built")

#endpoint to check if the backend is running
@app.get("/")
def root():
    return {"message": "Arena backend running"}

#data model for login request
class login_data(BaseModel):
    image: str #this str will be in base64

class register_data(BaseModel):
    name: str
    image: str

#endpoint for registering new users
@app.post("/register")
def auth_register(request: Request, response: Response, user_data: register_data):
    local_conn = db_pool.get_connection()
    sql_cursor = local_conn.cursor()

    sql_cursor.execute("SELECT uid FROM users WHERE name = %s", (user_data.name.strip(),))
    existing_user = sql_cursor.fetchone();

    if existing_user:
        sql_cursor.close()
        local_conn.close()
        return JSONResponse(status_code=400, content={"success": False, "reason": "username_taken"})

    new_uid = str(uuid.uuid4())
    new_encoding_dict = build_encodings_cache({new_uid: user_data.image})

    if new_uid not in new_encoding_dict:
        sql_cursor.close()
        local_conn.close()
        return JSONResponse(status_code=400, content={"success": False, "reason": "no_face_detected"})

    images_collection.insert_one({"uid": new_uid, "image_data": user_data.image, "scraped_at": datetime.now()})

    sql_cursor.execute("INSERT INTO users (uid, name, elo_rating, is_online) VALUES(%s, %s, %s, %s)", (new_uid, user_data.name, 1200, True)) 
    local_conn.commit()

    encodings_cache[new_uid] = new_encoding_dict[new_uid]

    new_session_id = secrets.token_urlsafe(32)
    active_sessions[new_session_id] = {"uid": new_uid, "name": user_data.name, "elo": 1200}
    response.set_cookie(key="session_id", value=new_session_id, httponly=True)

    sql_cursor.close()
    local_conn.close()

    return {"success": True, "uid": new_uid, "name": user_data.name, "elo": 1200}

#endpoint for login
@app.post("/login")
def auth_login(request: Request, response: Response, user_login_data: login_data):
    local_conn = db_pool.get_connection()
    sql_cursor = local_conn.cursor(dictionary=True)
    login_image_data = user_login_data.image

    #find the closest match for using the facial recognition module
    print("running facial recognition")
    closest_match = find_closest_match(login_image_data, encodings_cache)

    #check if a match is found
    if closest_match is not None:
        #if found, fetch user details from mysql
        sql_cursor.execute("SELECT uid, name, is_online, elo_rating FROM users WHERE uid = %s",(closest_match,))
        current_user = sql_cursor.fetchone()
        #check if the user exists
        if current_user is not None:
            #if user found, check if already logged in
            if current_user["is_online"]:
                #if already logged in, return an error response
                sql_cursor.close()
                local_conn.close()
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "reason": "already_logged_in"}
                )
            else:
                #else, update the user online status in mysql
                sql_cursor.execute("UPDATE users SET is_online = TRUE WHERE uid = %s",(closest_match,))
                local_conn.commit()
                #store user identity in server-side session vault and set only opaque session id in cookie
                new_session_id = secrets.token_urlsafe(32)
                active_sessions[new_session_id] = {
                    "uid": closest_match,
                    "name": current_user["name"],
                    "elo": current_user["elo_rating"],
                }
                response.set_cookie(
                    key="session_id",
                    value=new_session_id,
                    httponly=True,
                )
                sql_cursor.close()
                local_conn.close()
                return {"success": True, "uid": current_user["uid"], "name": current_user["name"], "elo": current_user["elo_rating"]}
        else:
            #if no user found ini mysql, return an error response
            sql_cursor.close()
            local_conn.close()
            return JSONResponse(
                status_code=404,
                content={"success": False, "reason": "user_not_found"}
            )
    else:
        #if no match is found, return an error response
        sql_cursor.close()
        local_conn.close()
        return JSONResponse(
            status_code=404,
            content={"success": False, "reason": "no_match"}
        )

#endpoint for logout
@app.post("/logout")
def logout(request: Request, response: Response):
    local_conn = db_pool.get_connection()
    sql_cursor = local_conn.cursor(dictionary=True)

    #get session id from cookie
    session_id = request.cookies.get("session_id")
    session_data = None
    
    if session_id is not None:
        session_data = active_sessions.pop(session_id, None)
    if session_data is None:
        sql_cursor.close()
        local_conn.close()
        error_response = JSONResponse(
            status_code=401,
            content={"success": False, "reason": "not_logged_in"}
        )
        error_response.delete_cookie(key="session_id") 
        return error_response

    response.delete_cookie(key="session_id")

    uid = session_data.get("uid")
    if uid is not None:
        #update online status in mysql
        sql_cursor.execute("UPDATE users SET is_online = FALSE WHERE uid = %s", (uid,))
        local_conn.commit()

    sql_cursor.close()
    local_conn.close()
    return {"success": True}


#endpoint to validate active backend session
@app.get("/me")
def get_current_user(request: Request):
    session_id = request.cookies.get("session_id")
    session_data = None
    if session_id is not None:
        session_data = active_sessions.get(session_id)
    if session_data is None:
        return JSONResponse(
            status_code=401,
            content={"success": False, "reason": "not_logged_in"}
        )

    uid = session_data.get("uid")
    sql_cursor = conn.cursor(dictionary=True)
    sql_cursor.execute("SELECT uid, name, elo_rating FROM users WHERE uid = %s", (uid,))
    current_user = sql_cursor.fetchone()
    sql_cursor.close()

    if current_user is None:
        if session_id:
            if session_id in active_sessions:
                del active_sessions[session_id]
        return JSONResponse(
            status_code=401,
            content={"success": False, "reason": "not_logged_in"}
        )

    #sync data from db to cookies
    session_data["name"] = current_user["name"]
    session_data["elo"] = current_user["elo_rating"]

    return {
        "success": True,
        "uid": current_user["uid"],
        "name": current_user["name"],
        "elo": current_user["elo_rating"],
    }

#endpoint for leaderboard
@app.get("/leaderboard")
def get_leaderboard():
    conn=db_pool.get_connection()
    sql_cursor=conn.cursor(dictionary=True)
    #fetch the leaderboard data from mysql ordered by elo_rating in descending order
    sql_cursor.execute("SELECT uid, name, elo_rating FROM users ORDER BY elo_rating DESC")
    leaderboard = sql_cursor.fetchall()
    sql_cursor.close()
    conn.close()
    return {"players": leaderboard}


#websockets part STARTS HERE->

#dictionary to store active rooms
active_rooms = {}

#list to store users in matches
users_in_game = {}

#manager class to handle live websocket connections
class ConnectionManager:
    def __init__(self):
        """init dict of active websocket connections with key as uid"""
        self.active_connections = {}
        self.uid_to_name = {}

    async def update_lobby(self):
        active_users_list = [{"uid": u, "name": self.uid_to_name.get(u), "in_game": users_in_game.get(u, False)} for u in self.active_connections.keys()]
        updated_list_json = {
            "action": "lobby_update",
            "users": active_users_list
        }
        await self.send_data_all(updated_list_json)

    async def connect(self, websocket: WebSocket, uid: str, name: str):
        """connect event"""
        await websocket.accept()

        if uid in self.active_connections:
            old_ws = self.active_connections[uid]
            try:
                # Tell the old tab it has been replaced
                await old_ws.close(code=4000, reason="session_take_over")
            except Exception:
                pass

        self.active_connections[uid] = websocket
        self.uid_to_name[uid] = name

        #set user to online in mysql on connect
        with conn.cursor() as sql_cursor:
            sql_cursor.execute("UPDATE users SET is_online = TRUE WHERE uid = %s", (uid,))
            conn.commit()

        await self.update_lobby()

    async def send_data(self, data_dict: dict, uid: str):
        """direct message to given uid"""
        if uid in self.active_connections:
            websocket = self.active_connections[uid]
            await websocket.send_json(data_dict)

    async def send_data_all(self, data_dict: dict):
        """send message to all live uid"""
        for uid in self.active_connections:
            websocket = self.active_connections[uid]
            await websocket.send_json(data_dict)

    async def disconnect(self, uid: str, websocket: WebSocket):
        """disconnect event"""
        if self.active_connections.get(uid) == websocket:
            self.active_connections.pop(uid, None)
            self.uid_to_name.pop(uid, None)
            users_in_game.pop(uid, None)
            #set user to offline in mysql on disconnect
            with conn.cursor() as sql_cursor:
                sql_cursor.execute("UPDATE users SET is_online = FALSE WHERE uid = %s", (uid,))
                conn.commit()
            
            await self.update_lobby()

#connection manager instance
manager = ConnectionManager()

pending_challenges = {}
challenge_timeout = 30 #challenge expires after 30 seconds

@app.websocket("/live")
async def live_websocket_endpoint(websocket: WebSocket):
    #get session id and get cookie data
    session_id = websocket.cookies.get("session_id")
    session_data = None
    if session_id is not None:
        session_data = active_sessions.get(session_id)
    if session_data is None:
        await websocket.close(code=1008)
        return

    uid = session_data.get("uid")
    name = session_data.get("name")
    if uid is None or name is None:
        await websocket.close(code=1008)
        return

    #register new websocket connection
    await manager.connect(websocket, uid, name)
    try:
        while True:
            #data_json is the message received from the frontend
            data_json = await websocket.receive_json()
            #if the action is send_challenge, send a receive_challenge message to the challenged user
            if data_json["action"] == "send_challenge":
                to_uid = data_json["to_uid"]

                #record the challenge in the server
                if to_uid not in pending_challenges:
                    pending_challenges[to_uid] = {}
                pending_challenges[to_uid][uid] = time.time()

                challenge_json = {
                    "action": "receive_challenge",
                    "from_uid": uid,
                    "from_name": manager.uid_to_name.get(uid),
                }
                await manager.send_data(challenge_json, data_json["to_uid"])
            #if the action is accept_challenge, send a redirect_to_room message to both users with the room details
            elif data_json["action"] == "accept_challenge":
                challenger_uid = data_json["to_uid"]
                receiver_uid = uid

                #validate that the challenge hasn't timed out and that it exists
                receiver_challenges = pending_challenges.get(receiver_uid, {})
                timestamp = receiver_challenges.get(challenger_uid)

                if timestamp is None or (time.time() - timestamp > challenge_timeout):
                    await manager.send_data({
                        "action": "challenge_error",
                        "message": "Challenge expired or invalid"
                    }, uid)
                    continue
                
                #checks if the challenger is still online
                if challenger_uid not in manager.active_connections:
                    await manager.send_data({
                        "action": "challenge_error",
                        "message": "The challenger disconnected"
                    }, uid)
                    #delete the dead challenge
                    del pending_challenges[receiver_uid][challenger_uid]
                    continue

                del pending_challenges[receiver_uid][challenger_uid]
                
                room_id = "room_" + "_".join(sorted([uid, challenger_uid]))
                if room_id not in active_rooms:
                    active_rooms[room_id] = RoomManager(room_id)
                    #make challenger x and receiver o
                    active_rooms[room_id].x = challenger_uid
                    active_rooms[room_id].o = receiver_uid
                    active_rooms[room_id].turn = challenger_uid
                room_json = {
                    "action": "redirect_to_room",
                    "room_id": room_id,
                    "player_x": challenger_uid,
                    "player1_uid": receiver_uid,
                    "player1_name": manager.uid_to_name.get(receiver_uid),
                    "player2_uid": challenger_uid,
                    "player2_name": manager.uid_to_name.get(challenger_uid),
                }
                await manager.send_data(room_json, uid)
                await manager.send_data(room_json, data_json["to_uid"])
            #if the action is decline_challenge, send a challenge_declined message to the challenged user
            elif data_json["action"] == "decline_challenge":
                pending_challenges.get(uid, {}).pop(data_json["to_uid"], None)
                decline_json = {
                    "action": "challenge_declined",
                    "from_uid": uid,
                    "from_name": manager.uid_to_name.get(uid),
                }
                await manager.send_data(decline_json, data_json["to_uid"])
            #if the action is cancel_challenge, send a challenge_cancelled message to the challenged user
            elif data_json["action"] == "cancel_challenge":
                pending_challenges.get(data_json["to_uid"], {}).pop(uid, None)
                cancel_json = {
                    "action": "challenge_cancelled",
                    "from_uid": uid,
                    "from_name": manager.uid_to_name.get(uid),
                }
                await manager.send_data(cancel_json, data_json["to_uid"])
    except WebSocketDisconnect:
        await manager.disconnect(uid, websocket)

#class to manage game room
class RoomManager:
    def __init__(self, room_id: str):
        """init players of this room"""
        self.room_id = room_id
        self.players = {}
        self.uid_to_name = {}
        self.uid_to_elo={}
        #board is a 1d array with -1 as init
        self.board = [-1, -1, -1, -1, -1, -1, -1, -1, -1]
        self.x = None
        self.o = None
        self.turn = None
        self.is_finished = False
    
    async def connect(self, websocket: WebSocket, uid: str, name: str, elo_val: int):
        """connect to room"""
        await websocket.accept()
        self.players[uid] = websocket
        self.uid_to_name[uid] = name
        self.uid_to_elo[uid]=elo_val
        users_in_game[uid] = True
        await manager.update_lobby()

        
    async def send_data(self, data_dict: dict, websocket: WebSocket):
        """direct message"""
        await websocket.send_json(data_dict)

    async def send_both(self, data_dict: dict):
        """send message to both"""
        for uid in self.players:
            websocket = self.players[uid]
            await websocket.send_json(data_dict)

    #function to check if the game has ended
    #this function returns the uid of the winner if there is a winner, "both" if it's a draw and None if the game is still going on
    async def getresult(self):
        #all winning patterns
        win_patterns = [[0, 1, 2], [3, 4, 5], [6, 7, 8], [0, 3, 6], [1, 4, 7], [2, 5, 8], [0, 4, 8], [2, 4, 6]]
        for pattern in win_patterns:
            #check if any of the winning patterns are occuring
            if self.board[pattern[0]] == self.board[pattern[1]] == self.board[pattern[2]] and self.board[pattern[0]] != -1:
                winner = self.board[pattern[0]]
                if winner == 'X':
                    return self.x 
                else:
                    return self.o
        if -1 not in self.board:
            return "both"
        return None

@app.websocket("/game/{room_id}")
async def game_websocket_endpoint(websocket: WebSocket, room_id: str):  
    #create the room if it doesnt exist yet
    if room_id not in active_rooms:
        await websocket.close(code=1008, reason="invalid room")
        return
    rmanager = active_rooms[room_id]
    #get session id and get cookie data
    session_id = websocket.cookies.get("session_id")
    session_data = None
    if session_id is not None:
        session_data = active_sessions.get(session_id)
    if session_data is None:
        await websocket.close(code=1008)
        return

    uid = session_data.get("uid")
    name = session_data.get("name")
    if uid is None or name is None:
        await websocket.close(code=1008)
        return
    if uid != rmanager.x and uid != rmanager.o:
        await websocket.close(code=1008, reason="unauthorized user for this room")
        return
    with conn.cursor(dictionary=True) as sql_cursor:
        sql_cursor.execute("SELECT elo_rating FROM users WHERE uid = %s", (uid,))
        db_user = sql_cursor.fetchone()
        player_elo = db_user["elo_rating"]
    await rmanager.connect(websocket, uid, name, player_elo)
    try:
        while True:
            #data_json is the message received from the frontend
            data_json = await websocket.receive_json()
            #if the action is play
            if data_json["action"] == "play":
                box_index = data_json.get("box_index")
                if not isinstance(box_index, int) or box_index < 0 or box_index > 8:
                    continue #drop the invalid packet

                #block the move if its not the players turn
                if rmanager.turn != uid:
                    block_json = {
                        "action": "block"
                    }
                    await rmanager.send_data(block_json, websocket)
                else:
                    #if it is the players turn, check if the move is invalid
                    if rmanager.board[data_json["box_index"]] != -1:
                        invalid_json = {
                            "action": "invalid"
                        }
                        await rmanager.send_data(invalid_json, websocket)
                    else:
                        #if the move is valid, check if the player plays x or o and update the board accordingly
                        if uid == rmanager.x:
                            rmanager.board[data_json["box_index"]] = "X"
                            rmanager.turn = rmanager.o
                        else:
                            rmanager.board[data_json["box_index"]] = "O"
                            rmanager.turn = rmanager.x
                        update_json = {
                            "action": "update_board",
                            "board": rmanager.board,
                            "next_turn": rmanager.turn
                        }   
                        #tell the frontend to display the new board (frontend can only print new board- cannot update game state directly)
                        await rmanager.send_both(update_json)
                        result = await rmanager.getresult()
                        #if result is not None that means the game has ended
                        if result is not None:
                            #guard
                            if rmanager.is_finished:
                                return
                            rmanager.is_finished = True 
                            end_json = {
                                "action": "game_end",
                                "result": result,
                            }
                            opponent_uid = rmanager.o if uid == rmanager.x else rmanager.x
                            if(result!='both'):
                                #calling the function to update the elos in the database
                                winner_flag=1 if result==rmanager.x else 0
                                e_x,e_o=elo.update_elo_when_match_ended(
                                    conn,rmanager.x,rmanager.o, 
                                    rmanager.uid_to_elo[rmanager.x], rmanager.uid_to_elo[rmanager.o], 
                                    winner_flag
                                )
                                end_json["new_elos"] = {rmanager.x: e_x, rmanager.o: e_o}
                            else:
                                #calling the function to update the elos in the database
                                e_x,e_o=elo.update_elo_when_match_ended(
                                    conn,rmanager.x,rmanager.o, 
                                    rmanager.uid_to_elo[rmanager.x],rmanager.uid_to_elo[rmanager.o], 
                                    -1
                                )
                                end_json["new_elos"] = {rmanager.x: e_x, rmanager.o: e_o}
                            #return the result
                            await rmanager.send_both(end_json)
                            #set users to not in game(free) and update the lobby
                            users_in_game[rmanager.x] = False
                            users_in_game[rmanager.o] = False
                            await manager.update_lobby()
                            #delete the room
                            del active_rooms[room_id]
                            return
        
            #if the action is resign, end the game and declare the other player as the winner
            elif data_json["action"] == "resign":
                #guard
                if rmanager.is_finished:
                    return
                rmanager.is_finished = True
                opponent_uid = rmanager.o if uid == rmanager.x else rmanager.x
                #if opponent hasn't connected to the socket yet, fetch their elo manually
                if opponent_uid not in rmanager.uid_to_elo:
                    temp_conn = db_pool.get_connection()
                    with temp_conn.cursor(dictionary=True) as temp_cursor:
                        temp_cursor.execute("SELECT elo_rating FROM users WHERE uid = %s", (opponent_uid,))
                        db_opp = temp_cursor.fetchone()
                        rmanager.uid_to_elo[opponent_uid] = db_opp["elo_rating"]

                    temp_conn.close()
                    
                #calling the function to update the elos in the database
                winner_flag = 0 if uid == rmanager.x else 1
                
                # calling the function to update the elos in the database
                e_x,e_o=elo.update_elo_when_match_ended(
                    conn, rmanager.x, rmanager.o, 
                    rmanager.uid_to_elo[rmanager.x], rmanager.uid_to_elo[rmanager.o], 
                    winner_flag
                )
                resign_json = {
                    "action": "game_end",
                    "result": rmanager.o if uid == rmanager.x else rmanager.x,
                    "reason": "resign_win_willing",
                    "new_elos": {rmanager.x: e_x, rmanager.o: e_o}
                }
                await rmanager.send_both(resign_json)
                #set users to not in game(free) and update the lobby
                users_in_game[rmanager.x] = False
                users_in_game[rmanager.o] = False
                await manager.update_lobby()
                #delete the room
                del active_rooms[room_id]
                return
            
    except WebSocketDisconnect:
        #if player disconnects, end the game and declare the other player as the winner
        rmanager.players.pop(uid, None)
        #guard
        if rmanager.is_finished:
            return
        rmanager.is_finished = True
        for remaining_uid in list(rmanager.players.keys()):
            remaining_ws = rmanager.players[remaining_uid]
            try:
                #calling the function to update the elos in the database
                e_x,e_o=elo.update_elo_when_ragequit(
                    conn,rmanager.x,rmanager.o,uid, 
                    rmanager.uid_to_elo[rmanager.x], rmanager.uid_to_elo[rmanager.o]
                )
                # tell the other player that the game has ended
                resign_json = {
                    "action": "game_end",
                    "result": remaining_uid,
                    "reason": "resign_win_disconnect",
                    "new_elos": {rmanager.x: e_x, rmanager.o: e_o}
                }
                await rmanager.send_data(resign_json, remaining_ws)
                await remaining_ws.close()
            except Exception:
                pass                
        #check if the room is in active rooms before deleting since its possible that the room has already been deleted if both players disconnected around the same time
        if room_id in active_rooms:
            #set users to not in game(free) and update the lobby
            users_in_game[rmanager.x] = False
            users_in_game[rmanager.o] = False
            await manager.update_lobby()
            #delete the room
            del active_rooms[room_id]