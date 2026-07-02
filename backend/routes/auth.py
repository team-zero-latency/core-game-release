from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
import secrets
import uuid
from datetime import datetime

from database import db_pool, images_collection
from state import active_sessions, encodings_cache
from models import login_data, register_data, find_closest_match

router = APIRouter()

@router.post("/register")
def auth_register(request: Request, response: Response, user_data: register_data):
    local_conn = db_pool.get_connection()
    sql_cursor = local_conn.cursor()

    sql_cursor.execute("SELECT uid FROM users WHERE name = %s", (user_data.name.strip(),))
    existing_user = sql_cursor.fetchone()

    if existing_user:
        sql_cursor.close()
        local_conn.close()
        return JSONResponse(status_code=400, content={"success": False, "reason": "username_taken"})

    new_uid = str(uuid.uuid4())
    images_collection.insert_one({"uid": new_uid, "image_data": user_data.image, "scraped_at": datetime.now()})

    sql_cursor.execute("INSERT INTO users (uid, name, elo_rating, is_online) VALUES(%s, %s, %s, %s)", (new_uid, user_data.name, 1200, True)) 
    local_conn.commit()

    encodings_cache[new_uid] = user_data.embedding

    new_session_id = secrets.token_urlsafe(32)
    active_sessions[new_session_id] = {"uid": new_uid, "name": user_data.name, "elo": 1200}
    response.set_cookie(key="session_id", value=new_session_id, httponly=True)

    sql_cursor.close()
    local_conn.close()
    return {"success": True, "uid": new_uid, "name": user_data.name, "elo": 1200}

@router.post("/login")
def auth_login(request: Request, response: Response, user_login_data: login_data):
    local_conn = db_pool.get_connection()
    sql_cursor = local_conn.cursor(dictionary=True)

    closest_match = find_closest_match(user_login_data.embedding, encodings_cache)

    if closest_match is not None:
        sql_cursor.execute("SELECT uid, name, is_online, elo_rating FROM users WHERE uid = %s",(closest_match,))
        current_user = sql_cursor.fetchone()
        
        if current_user is not None:
            if current_user["is_online"]:
                sql_cursor.close()
                local_conn.close()
                return JSONResponse(status_code=400, content={"success": False, "reason": "already_logged_in"})
            else:
                sql_cursor.execute("UPDATE users SET is_online = TRUE WHERE uid = %s",(closest_match,))
                local_conn.commit()
                
                new_session_id = secrets.token_urlsafe(32)
                active_sessions[new_session_id] = {
                    "uid": closest_match,
                    "name": current_user["name"],
                    "elo": current_user["elo_rating"],
                }
                response.set_cookie(key="session_id", value=new_session_id, httponly=True)
                
                sql_cursor.close()
                local_conn.close()
                return {"success": True, "uid": current_user["uid"], "name": current_user["name"], "elo": current_user["elo_rating"]}
        else:
            sql_cursor.close()
            local_conn.close()
            return JSONResponse(status_code=404, content={"success": False, "reason": "user_not_found"})
    else:
        sql_cursor.close()
        local_conn.close()
        return JSONResponse(status_code=404, content={"success": False, "reason": "no_match"})

@router.post("/logout")
def logout(request: Request, response: Response):
    local_conn = db_pool.get_connection()
    sql_cursor = local_conn.cursor(dictionary=True)

    session_id = request.cookies.get("session_id")
    session_data = None
    
    if session_id is not None:
        session_data = active_sessions.pop(session_id, None)
    if session_data is None:
        sql_cursor.close()
        local_conn.close()
        error_response = JSONResponse(status_code=401, content={"success": False, "reason": "not_logged_in"})
        error_response.delete_cookie(key="session_id") 
        return error_response

    response.delete_cookie(key="session_id")

    uid = session_data.get("uid")
    if uid is not None:
        sql_cursor.execute("UPDATE users SET is_online = FALSE WHERE uid = %s", (uid,))
        local_conn.commit()

    sql_cursor.close()
    local_conn.close()
    return {"success": True}

@router.get("/me")
def get_current_user(request: Request):
    session_id = request.cookies.get("session_id")
    session_data = None
    
    if session_id is not None:
        session_data = active_sessions.get(session_id)
    if session_data is None:
        return JSONResponse(status_code=401, content={"success": False, "reason": "not_logged_in"})

    uid = session_data.get("uid")
    local_conn = db_pool.get_connection()
    sql_cursor = local_conn.cursor(dictionary=True)
    sql_cursor.execute("SELECT uid, name, elo_rating FROM users WHERE uid = %s", (uid,))
    current_user = sql_cursor.fetchone()
    sql_cursor.close()
    local_conn.close()

    if current_user is None:
        if session_id and session_id in active_sessions:
            del active_sessions[session_id]
        return JSONResponse(status_code=401, content={"success": False, "reason": "not_logged_in"})

    session_data["name"] = current_user["name"]
    session_data["elo"] = current_user["elo_rating"]

    return {
        "success": True,
        "uid": current_user["uid"],
        "name": current_user["name"],
        "elo": current_user["elo_rating"],
    }

@router.get("/leaderboard")
def get_leaderboard():
    local_conn = db_pool.get_connection()
    sql_cursor = local_conn.cursor(dictionary=True)
    sql_cursor.execute("SELECT uid, name, elo_rating FROM users ORDER BY elo_rating DESC")
    leaderboard = sql_cursor.fetchall()
    sql_cursor.close()
    local_conn.close()
    return {"players": leaderboard}