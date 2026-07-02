import os
from pymongo import MongoClient
from dotenv import load_dotenv
from mysql.connector import pooling

load_dotenv()

#connect to mongodb
mongo_client = MongoClient(os.getenv("MONGO_URI"), serverSelectionTimeoutMS=2000)
mongo_db = mongo_client["arena_db"]
images_collection = mongo_db["profile_images"]

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

def init_db():
    local_conn = db_pool.get_connection()
    sql_cursor = local_conn.cursor()

    # Create users and matches tables
    sql_cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            uid VARCHAR(50) PRIMARY KEY,
            name VARCHAR(200) UNIQUE NOT NULL,
            elo_rating INT NOT NULL DEFAULT 1200,
            is_online BOOLEAN NOT NULL DEFAULT FALSE
        )
    """)

    sql_cursor.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            match_id INT AUTO_INCREMENT PRIMARY KEY,
            player_x_uid VARCHAR(50),
            player_o_uid VARCHAR(50),
            winner_uid VARCHAR(50),
            forfeit BOOLEAN DEFAULT FALSE,
            played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )                       
    """)

    # Reset online statuses in case of improper server shutdown
    sql_cursor.execute("UPDATE users SET is_online = FALSE")

    local_conn.commit()
    sql_cursor.close()
    local_conn.close()

    # Intialise MongoDB indexes
    images_collection.create_index("uid", unique=True)

def load_encodings(cache):
    print("Loading embeddings from MongoDB...")
    db_profiles = list(images_collection.find())
    for doc in db_profiles:
        if "embedding" in doc:
            cache[doc["uid"]] = doc["embedding"]
    print("Embeddings loaded successfully:", len(cache))