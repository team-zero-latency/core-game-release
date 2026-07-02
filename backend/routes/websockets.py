from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import time

from database import db_pool
from state import active_sessions, active_rooms, users_in_game
from socket_manager import manager, RoomManager
import elo

router = APIRouter()

pending_challenges = {}
challenge_timeout = 30

@router.websocket("/live")
async def live_websocket_endpoint(websocket: WebSocket):
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

    await manager.connect(websocket, uid, name)
    try:
        while True:
            data_json = await websocket.receive_json()
            if data_json["action"] == "send_challenge":
                to_uid = data_json["to_uid"]
                if to_uid not in pending_challenges:
                    pending_challenges[to_uid] = {}
                pending_challenges[to_uid][uid] = time.time()

                challenge_json = {
                    "action": "receive_challenge",
                    "from_uid": uid,
                    "from_name": manager.uid_to_name.get(uid),
                }
                await manager.send_data(challenge_json, data_json["to_uid"])
                
            elif data_json["action"] == "accept_challenge":
                challenger_uid = data_json["to_uid"]
                receiver_uid = uid

                receiver_challenges = pending_challenges.get(receiver_uid, {})
                timestamp = receiver_challenges.get(challenger_uid)

                if timestamp is None or (time.time() - timestamp > challenge_timeout):
                    await manager.send_data({"action": "challenge_error", "message": "Challenge expired or invalid"}, uid)
                    continue
                
                if challenger_uid not in manager.active_connections:
                    await manager.send_data({"action": "challenge_error", "message": "The challenger disconnected"}, uid)
                    del pending_challenges[receiver_uid][challenger_uid]
                    continue

                del pending_challenges[receiver_uid][challenger_uid]
                
                room_id = "room_" + "_".join(sorted([uid, challenger_uid]))
                if room_id not in active_rooms:
                    active_rooms[room_id] = RoomManager(room_id)
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
                
            elif data_json["action"] == "decline_challenge":
                pending_challenges.get(uid, {}).pop(data_json["to_uid"], None)
                decline_json = {
                    "action": "challenge_declined",
                    "from_uid": uid,
                    "from_name": manager.uid_to_name.get(uid),
                }
                await manager.send_data(decline_json, data_json["to_uid"])
                
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


@router.websocket("/game/{room_id}")
async def game_websocket_endpoint(websocket: WebSocket, room_id: str):  
    if room_id not in active_rooms:
        await websocket.close(code=1008, reason="invalid room")
        return
    rmanager = active_rooms[room_id]
    
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
        
    local_conn = db_pool.get_connection()
    with local_conn.cursor(dictionary=True) as sql_cursor:
        sql_cursor.execute("SELECT elo_rating FROM users WHERE uid = %s", (uid,))
        db_user = sql_cursor.fetchone()
        player_elo = db_user["elo_rating"]
    local_conn.close()
    
    await rmanager.connect(websocket, uid, name, player_elo)
    
    try:
        while True:
            data_json = await websocket.receive_json()
            if data_json["action"] == "play":
                box_index = data_json.get("box_index")
                if not isinstance(box_index, int) or box_index < 0 or box_index > 8:
                    continue 

                if rmanager.turn != uid:
                    await rmanager.send_data({"action": "block"}, websocket)
                else:
                    if rmanager.board[data_json["box_index"]] != -1:
                        await rmanager.send_data({"action": "invalid"}, websocket)
                    else:
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
                        await rmanager.send_both(update_json)
                        
                        result = await rmanager.getresult()
                        if result is not None:
                            if rmanager.is_finished:
                                return
                            rmanager.is_finished = True 
                            end_json = {
                                "action": "game_end",
                                "result": result,
                            }
                            
                            local_conn = db_pool.get_connection()
                            if result != 'both':
                                winner_flag = 1 if result == rmanager.x else 0
                                e_x, e_o = elo.update_elo_when_match_ended(
                                    local_conn, rmanager.x, rmanager.o, 
                                    rmanager.uid_to_elo[rmanager.x], rmanager.uid_to_elo[rmanager.o], 
                                    winner_flag
                                )
                            else:
                                e_x, e_o = elo.update_elo_when_match_ended(
                                    local_conn, rmanager.x, rmanager.o, 
                                    rmanager.uid_to_elo[rmanager.x], rmanager.uid_to_elo[rmanager.o], 
                                    -1
                                )
                            local_conn.close()
                            
                            end_json["new_elos"] = {rmanager.x: e_x, rmanager.o: e_o}
                            await rmanager.send_both(end_json)
                            
                            users_in_game[rmanager.x] = False
                            users_in_game[rmanager.o] = False
                            await manager.update_lobby()
                            
                            del active_rooms[room_id]
                            return
        
            elif data_json["action"] == "resign":
                if rmanager.is_finished:
                    return
                rmanager.is_finished = True
                opponent_uid = rmanager.o if uid == rmanager.x else rmanager.x
                
                if opponent_uid not in rmanager.uid_to_elo:
                    temp_conn = db_pool.get_connection()
                    with temp_conn.cursor(dictionary=True) as temp_cursor:
                        temp_cursor.execute("SELECT elo_rating FROM users WHERE uid = %s", (opponent_uid,))
                        db_opp = temp_cursor.fetchone()
                        rmanager.uid_to_elo[opponent_uid] = db_opp["elo_rating"]
                    temp_conn.close()
                    
                winner_flag = 0 if uid == rmanager.x else 1
                
                local_conn = db_pool.get_connection()
                e_x, e_o = elo.update_elo_when_match_ended(
                    local_conn, rmanager.x, rmanager.o, 
                    rmanager.uid_to_elo[rmanager.x], rmanager.uid_to_elo[rmanager.o], 
                    winner_flag
                )
                local_conn.close()
                
                resign_json = {
                    "action": "game_end",
                    "result": rmanager.o if uid == rmanager.x else rmanager.x,
                    "reason": "resign_win_willing",
                    "new_elos": {rmanager.x: e_x, rmanager.o: e_o}
                }
                await rmanager.send_both(resign_json)
                
                users_in_game[rmanager.x] = False
                users_in_game[rmanager.o] = False
                await manager.update_lobby()
                
                del active_rooms[room_id]
                return
            
    except WebSocketDisconnect:
        rmanager.players.pop(uid, None)
        if rmanager.is_finished:
            return
        rmanager.is_finished = True
        
        local_conn = db_pool.get_connection()
        for remaining_uid in list(rmanager.players.keys()):
            remaining_ws = rmanager.players[remaining_uid]
            try:
                e_x, e_o = elo.update_elo_when_ragequit(
                    local_conn, rmanager.x, rmanager.o, uid, 
                    rmanager.uid_to_elo[rmanager.x], rmanager.uid_to_elo[rmanager.o]
                )
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
        local_conn.close()
                       
        if room_id in active_rooms:
            users_in_game[rmanager.x] = False
            users_in_game[rmanager.o] = False
            await manager.update_lobby()
            del active_rooms[room_id]