import csv
import requests
import mysql.connector
from pymongo import MongoClient
import base64
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()
# connecting to sql
conn=mysql.connector.connect(
    host="localhost",
    user=os.getenv("MYSQL_USER"),
    password=os.getenv("MYSQL_PASSWORD"),
    database="arena_db",
    autocommit=True
)
sql_cursor=conn.cursor()
# connecting to mongodb
mongo_client = MongoClient(os.getenv("MONGO_URI"), serverSelectionTimeoutMS=2000)
mongo_client.server_info() 
mongo_db = mongo_client["arena_db"]
images_collection = mongo_db["profile_images"]
# reading csv file
with open('batch_data.csv',mode='r') as file:
    reader=csv.DictReader(file);
    for row in reader:
        uid=row['uid']
        name=row['name']
        website=row['website_url']
        try:
            response=requests.get(f"https://{website}/images/pfp.jpg",timeout=5)#sending request to the site
            if(response.status_code==200):#if the request is successful
                sql_query = "INSERT IGNORE INTO users (uid,name) VALUES (%s, %s)"
                sql_cursor.execute(sql_query,(uid, name))#insert into the table 
                conn.commit()
                base64_image = base64.b64encode(response.content).decode('utf-8')#way to store image
                images_collection.update_one(#update mongdb
                {"uid":uid},
                {"$set":{"image_data":base64_image,"scraped_at":datetime.now()}},
                upsert=True
                )
            else:
                print(f" Skipped user {uid}: Image missing (HTTP {response.status_code})")
                #if connection to the site failed
        except requests.exceptions.RequestException as e:
            print(f"Failed to connect to {website}/images/pfp.jpg for user {uid}: {e}")
sql_cursor.close()
conn.close()
mongo_client.close()