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