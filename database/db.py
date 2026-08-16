import aiosqlite
from motor.motor_asyncio import AsyncIOMotorClient
from config import DATABASE_TYPE, MONGO_URI, DATABASE_NAME, SQLITE_DATABASE

class Database:
    def __init__(self):
        self.mongo = None
        self.db = None
        self.sqlite_path = SQLITE_DATABASE

    async def connect(self):
        if DATABASE_TYPE.lower() == "mongodb":
            self.mongo = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            await self.mongo.admin.command("ping")
            self.db = self.mongo[DATABASE_NAME]
            await self.db.users.create_index("user_id", unique=True)
            await self.db.channels.create_index([("owner_id", 1), ("channel_id", 1)], unique=True)
        else:
            self.sqlite = await aiosqlite.connect(self.sqlite_path)
            await self.sqlite.executescript('''
            CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, username TEXT, blocked INTEGER DEFAULT 0, first_seen TEXT, last_seen TEXT);
            CREATE TABLE IF NOT EXISTS channels(channel_id INTEGER PRIMARY KEY, owner_id INTEGER, title TEXT, username TEXT, config TEXT);
            CREATE TABLE IF NOT EXISTS admins(user_id INTEGER PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS stats(key TEXT PRIMARY KEY, value INTEGER DEFAULT 0);
            ''')
            await self.sqlite.commit()

    async def user_upsert(self, user_id, username):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        if DATABASE_TYPE.lower() == "mongodb":
            await self.db.users.update_one({"user_id": user_id}, {"$set": {"username": username, "last_seen": now}, "$setOnInsert": {"first_seen": now, "blocked": False}}, upsert=True)
        else:
            await self.sqlite.execute("INSERT INTO users(user_id,username,first_seen,last_seen) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,last_seen=excluded.last_seen", (user_id, username, now, now)); await self.sqlite.commit()

    async def is_admin(self, user_id):
        from config import OWNER_ID
        if user_id == OWNER_ID: return True
        if DATABASE_TYPE.lower() == "mongodb": return bool(await self.db.admins.find_one({"user_id": user_id}))
        cur = await self.sqlite.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,)); return await cur.fetchone() is not None

    async def add_admin(self, user_id):
        if DATABASE_TYPE.lower() == "mongodb": await self.db.admins.update_one({"user_id": user_id}, {"$set": {"user_id": user_id}}, upsert=True)
        else: await self.sqlite.execute("INSERT OR IGNORE INTO admins(user_id) VALUES(?)", (user_id,)); await self.sqlite.commit()

    async def del_admin(self, user_id):
        if DATABASE_TYPE.lower() == "mongodb": await self.db.admins.delete_one({"user_id": user_id})
        else: await self.sqlite.execute("DELETE FROM admins WHERE user_id=?", (user_id,)); await self.sqlite.commit()

    async def save_channel(self, owner_id, channel_id, title, username, config):
        if DATABASE_TYPE.lower() == "mongodb":
            await self.db.channels.update_one({"owner_id": owner_id, "channel_id": channel_id}, {"$set": {"title": title, "username": username, "config": config}}, upsert=True)
        else:
            await self.sqlite.execute("INSERT OR REPLACE INTO channels(channel_id,owner_id,title,username,config) VALUES(?,?,?,?,?)", (channel_id,owner_id,title,username,config)); await self.sqlite.commit()

    async def get_channel(self, channel_id):
        if DATABASE_TYPE.lower() == "mongodb": return await self.db.channels.find_one({"channel_id": channel_id})
        cur = await self.sqlite.execute("SELECT channel_id,owner_id,title,username,config FROM channels WHERE channel_id=?", (channel_id,)); row=await cur.fetchone();
        return None if not row else {"channel_id":row[0],"owner_id":row[1],"title":row[2],"username":row[3],"config":row[4]}

    async def list_channels(self, owner_id=None):
        if DATABASE_TYPE.lower() == "mongodb":
            q={} if owner_id is None else {"owner_id":owner_id}; return await self.db.channels.find(q).to_list(1000)
        q="SELECT channel_id,owner_id,title,username,config FROM channels"; args=()
        if owner_id is not None: q += " WHERE owner_id=?"; args=(owner_id,)
        cur=await self.sqlite.execute(q,args); rows=await cur.fetchall(); return [{"channel_id":r[0],"owner_id":r[1],"title":r[2],"username":r[3],"config":r[4]} for r in rows]

    async def delete_channel(self, channel_id, owner_id):
        if DATABASE_TYPE.lower() == "mongodb": await self.db.channels.delete_one({"channel_id":channel_id,"owner_id":owner_id})
        else: await self.sqlite.execute("DELETE FROM channels WHERE channel_id=? AND owner_id=?",(channel_id,owner_id)); await self.sqlite.commit()

    async def counts(self):
        if DATABASE_TYPE.lower() == "mongodb": return {"users":await self.db.users.count_documents({}),"channels":await self.db.channels.count_documents({})}
        a=await (await self.sqlite.execute("SELECT COUNT(*) FROM users")).fetchone(); b=await (await self.sqlite.execute("SELECT COUNT(*) FROM channels")).fetchone(); return {"users":a[0],"channels":b[0]}
