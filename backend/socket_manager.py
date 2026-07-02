from fastapi import WebSocket
from database import db_pool
from state import users_in_game

class ConnectionManager:
    def __init__(self):
        """init dict of active websocket connections with key as uid"""
        self.active_connections: dict[str, WebSocket] = {}
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

        # set user to online in mysql on connect
        local_conn = db_pool.get_connection()
        with local_conn.cursor() as sql_cursor:
            sql_cursor.execute("UPDATE users SET is_online = TRUE WHERE uid = %s", (uid,))
            local_conn.commit()
        local_conn.close()

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
            
            # set user to offline in mysql on disconnect
            local_conn = db_pool.get_connection()
            with local_conn.cursor() as sql_cursor:
                sql_cursor.execute("UPDATE users SET is_online = FALSE WHERE uid = %s", (uid,))
                local_conn.commit()
            local_conn.close()
            
            await self.update_lobby()

# Global connection manager instance
manager = ConnectionManager()

class RoomManager:
    def __init__(self, room_id: str):
        """init players of this room"""
        self.room_id = room_id
        self.players = {}
        self.uid_to_name = {}
        self.uid_to_elo = {}
        # board is a 1d array with -1 as init
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
        self.uid_to_elo[uid] = elo_val
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

    # function to check if the game has ended
    async def getresult(self):
        # all winning patterns
        win_patterns = [[0, 1, 2], [3, 4, 5], [6, 7, 8], [0, 3, 6], [1, 4, 7], [2, 5, 8], [0, 4, 8], [2, 4, 6]]
        for pattern in win_patterns:
            if self.board[pattern[0]] == self.board[pattern[1]] == self.board[pattern[2]] and self.board[pattern[0]] != -1:
                winner = self.board[pattern[0]]
                if winner == 'X':
                    return self.x 
                else:
                    return self.o
        if -1 not in self.board:
            return "both"
        return None