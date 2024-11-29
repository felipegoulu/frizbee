"""
Database Connection Manager

Este módulo maneja las conexiones a la base de datos PostgreSQL usando un pool de conexiones.
Proporciona una forma eficiente y segura de compartir conexiones entre diferentes partes de la aplicación.

Características principales:
- Usa ThreadedConnectionPool para manejar múltiples conexiones concurrentes
- Cachea el pool de conexiones usando st.cache_resource
- Implementa context manager para manejo seguro de conexiones
- Configura autocommit para optimizar queries de lectura
"""
import os
from contextlib import contextmanager
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
import streamlit as st
import json
from psycopg2.extras import Json

@st.cache_resource
def init_connection_pool():
    """Initialize and cache the database connection pool"""
    return ThreadedConnectionPool(
        minconn=1,
        maxconn=20,
        dsn=os.getenv('DATABASE_URL')
    )

# Get connection pool on startup
pool = init_connection_pool()

@contextmanager
def get_db_connection():
    """Get a connection from the cached pool"""
    conn = None
    try:
        conn = pool.getconn()
        conn.set_session(autocommit=True)
        yield conn
    finally:
        if conn is not None:
            pool.putconn(conn)

def save_cart(user_id, cart_items):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_cart (user_id, cart_items, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id) 
                DO UPDATE SET 
                    cart_items = %s,
                    updated_at = CURRENT_TIMESTAMP
            """, (user_id, Json(cart_items), Json(cart_items)))
            conn.commit()

def load_cart(user_id):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT cart_items FROM user_cart 
                WHERE user_id = %s
            """, (user_id,))
            result = cur.fetchone()
            return result['cart_items'] if result else []

