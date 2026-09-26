from sqlalchemy import create_engine

from app.config import DATABASE_URL

# pool_pre_ping avoids stale-connection errors against Neon's pooled endpoint
# after the app has been idle for a while.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
