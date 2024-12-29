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
from langchain_core.messages import AIMessage, HumanMessage

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

def complete_cart(user_id):
    """Mark current cart as completed and create a new one"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Mark current cart as completed
            cur.execute("""
                UPDATE user_cart 
                SET status = 'completado',
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s AND status = 'en_proceso'
            """, (user_id,))
            
            cur.execute("""
                INSERT INTO user_cart
                (user_id, cart_items, status, created_at, updated_at)
                VALUES 
                (%s, %s::jsonb, 'en_proceso', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (user_id, '[]'))
            
            conn.commit()

def change_messages_status(user_id):
    """Mark chat messages as completed"""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Mark chat messages as completed
            cur.execute("""
                UPDATE chat_messages
                SET status = 'completado',
                    updated_at = CURRENT_TIMESTAMP
                WHERE session_id = %s AND status = 'en_proceso'
            """, (user_id,)) 
            conn.commit()

def save_cart(user_id, cart_items):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_cart
                (user_id, cart_items, status, created_at, updated_at)
                VALUES 
                (%s, %s::jsonb, 'completado', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING cart_items
            """, (user_id, cart_items))
            conn.commit()
            

def load_cart(user_id):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT cart_items FROM user_cart 
                WHERE user_id = %s AND status = 'en_proceso'
            """, (user_id,))
            result = cur.fetchone()

            if not result:
                # Si no existe un carrito activo, crear uno nuevo
                cur.execute("""
                    INSERT INTO user_cart
                    (user_id, cart_items, status, created_at, updated_at)
                    VALUES 
                    (%s, %s::jsonb, 'en_proceso', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING cart_items
                """, (user_id, '[]'))
                result = cur.fetchone()
            
            return result['cart_items']


def load_preferences(user_id: str) -> str:
    """
    Load user preferences from the database.
    Args:
        user_id: The user's ID
    Returns:
        String containing user preferences
    """
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT content 
                FROM ai_memory 
                WHERE user_id = %s AND type = 'preferences'
                ORDER BY created_at DESC
                LIMIT 1
            """, (user_id,))
            memory = cur.fetchone()
            
            if not memory:
                # Insert a new row if no preferences are found
                cur.execute("""
                    INSERT INTO ai_memory (user_id, content, type, created_at, updated_at)
                    VALUES (%s, %s, 'preferences',CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING content
                """, (user_id, ''))
                memory = cur.fetchone()                
                conn.commit()
            return memory['content']


def save_preferences(user_id, preferences):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            UPDATE ai_memory 
                SET content = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s AND type = 'preferences' 
            """, (preferences, user_id))
            conn.commit()

# Database functions
def load_messages_en_proceso(session_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT role, content FROM chat_messages 
                    WHERE session_id = %s AND status = 'en_proceso' 
                    ORDER BY created_at
                """, (session_id,))
                messages = cur.fetchall()
                
                return [
                    AIMessage(content=msg['content']) if msg['role'] == 'assistant'
                    else HumanMessage(content=msg['content'])
                    for msg in messages
                ]
    except Exception as e:
        st.error(f"Error loading chat history: {e}")
        return []

def add_summary_db(user_id, summary_content):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ai_memory (user_id, content, type, created_at, updated_at)
                VALUES (%s, %s, 'summary', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (user_id, summary_content))
            conn.commit()  # Agregamos el commit nuevamente

def load_summaries(user_id):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT content, created_at FROM ai_memory 
                WHERE user_id = %s AND type = 'summary'
                ORDER BY created_at DESC
            """, (user_id,))
            results = cur.fetchall() # list of summaries
            conn.commit()
            
            return results

def load_old_carts(user_id):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT cart_items, updated_at FROM user_cart 
                WHERE user_id = %s AND status = 'completado' AND cart_items != '[]'::jsonb
                ORDER BY updated_at DESC
            """, (user_id,))
            results = cur.fetchall() # list of summaries
            conn.commit()
            
            return results

from datetime import datetime

def save_message(session_id, role, content, msg_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO chat_messages (session_id, role, content, created_at, status, msg_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (session_id, role, content, datetime.now(), "en_proceso", msg_id))
            conn.commit()

# Database functions
def load_chat_history(session_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT role, content FROM chat_messages 
                    WHERE session_id = %s 
                    ORDER BY created_at
                """, (session_id,))
                messages = cur.fetchall()
                
                return [
                    AIMessage(content=msg['content']) if msg['role'] == 'assistant'
                    else HumanMessage(content=msg['content'])
                    for msg in messages
                ]
    except Exception as e:
        st.error(f"Error loading chat history: {e}")
        return []

# Database functions
def check_duplicated(session_id, msg_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT session_id FROM chat_messages 
                    WHERE session_id = %s and msg_id = %s 
                """, (session_id,msg_id))
                messages = cur.fetchone()
                
                return messages is not None # Retorna True si hay un duplicado 
                
    except Exception as e:
        st.error(f"Error loading chat history: {e}")
        return []


def update_key(session_id, key):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    UPDATE keys
                    SET updated_at = CURRENT_TIMESTAMP, key= %s
                    WHERE user_id = %s 
                """, (key, session_id))

                if cur.rowcount == 0:
                    # Si no existe la clave, crear una nueva fila
                    cur.execute("""
                        INSERT INTO keys (user_id, key,created_at, updated_at)
                        VALUES (%s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        RETURNING key
                    """, (session_id, key))  # Cambia 'default_key_value' según sea necesario
                    conn.commit()
                
    except Exception as e:
        st.error(f"Error loading chat history: {e}")
        return []


def load_key(user_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT key FROM keys
                    WHERE user_id = %s 
                """, (user_id,))
                key = cur.fetchone()
            
                if key is None:
                    # Si no se encuentra la clave, crear una nueva clave vacía
                    cur.execute("""
                        INSERT INTO keys (user_id, key, created_at, updated_at)
                        VALUES (%s, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        RETURNING key
                    """, (user_id,))
                    key = cur.fetchone()  # Obtener la nueva clave vacía
                    conn.commit()
                return key 
                
    except Exception as e:
        st.error(f"Error loading chat history: {e}")
        return []


def load_key_message(user_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT cart FROM keys
                    WHERE user_id = %s 
                """, (user_id,))
                key = cur.fetchone()
                
                return key 
                
    except Exception as e:
        st.error(f"Error loading chat history: {e}")
        return []
    
