import sys
sys.setrecursionlimit(1500)

from dotenv import load_dotenv
import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage
import asyncio
import nltk
import psycopg2
from psycopg2.pool import ThreadedConnectionPool

from psycopg2.extras import RealDictCursor
import os
from datetime import datetime
import uuid
from contextlib import contextmanager

# Load environment variables
load_dotenv()
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

# Actualizar el CSS personalizado
st.markdown("""
    <style>
    /* Estilos existentes */
    .stButton button {
        text-align: left;
        height: auto;
        padding: 10px;
        white-space: pre-wrap;
    }
    
    .stButton button p {
        font-size: 0.8em;
        margin: 0;
        opacity: 0.8;
    }

    [data-testid="column"]:nth-of-type(2) .stButton button {
        text-align: center;
        padding: 10px 5px;
    }

    /* Nuevos estilos */
    .cart-button {
        background: linear-gradient(to right, #FF4B4B, #FF6B6B);
        color: white;
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
        text-align: center;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    }

    .cart-count {
        background: white;
        color: #FF4B4B;
        border-radius: 50%;
        padding: 2px 8px;
        margin-left: 8px;
        font-weight: bold;
    }

    .sidebar-title {
        font-size: 1.5em;
        font-weight: bold;
        margin-bottom: 20px;
        color: #333;
    }

    .new-chat-button {
        border: 2px solid #4CAF50;
        color: #4CAF50;
        background: white;
        border-radius: 8px;
        transition: all 0.3s;
    }

    .new-chat-button:hover {
        background: #4CAF50;
        color: white;
    }

    .history-item {
        background: #f7f7f7;
        border-radius: 8px;
        margin: 5px 0;
        transition: all 0.2s;
    }

    .history-item:hover {
        background: #e9e9e9;
    }
    </style>
""", unsafe_allow_html=True)

# NLTK setup
@st.cache_resource
def download_nltk_resources():
    nltk.download('punkt_tab')
   
download_nltk_resources()

from astream_events_handler import invoke_our_graph

# Constants
USER_AVATAR = "🧑🏻"
BOT_AVATAR = "🤖"

from db import get_db_connection

# Add this new function to get user preferences
def get_user_preferences(session_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get preferences
                cur.execute("""
                    SELECT content, context 
                    FROM ai_memory 
                    WHERE user_id = %s AND "long_term"
                    ORDER BY created_at DESC
                """, (session_id,))
                memories = cur.fetchall()
                
                if not memories:
                    return "No hay preferencias guardadas aún."
                
                # Format memories into a readable string
                preferences = "\nPREFERENCIAS DEL USUARIO:\n"
                for memory in memories:
                    preferences += f"- {memory['content']} ({memory['context']})\n"
                
                return preferences
    except Exception as e:
        print(f"Error getting preferences: {e}")
        return "No hay preferencias del usuario."

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

def save_message(session_id, role, content):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO chat_messages (session_id, role, content, created_at, status)
                VALUES (%s, %s, %s, %s, %s)
            """, (session_id, role, content, datetime.now(), "en_proceso"))
            conn.commit()

def get_all_sessions():
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT DISTINCT ON (session_id) 
                    session_id,
                    content as last_message,
                    created_at
                FROM chat_messages
                ORDER BY session_id, created_at DESC
            """)
            return cur.fetchall()

# Initialize session state
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = load_chat_history(st.session_state.session_id)

from db import load_cart, load_preferences, load_summaries, load_old_carts
if "my_cart" not in st.session_state:
    st.session_state.my_cart = load_cart(st.session_state.session_id)

if "user_preferences" not in st.session_state:
    st.session_state.user_preferences = load_preferences(st.session_state.session_id)

# Sidebar with conversation management
with st.sidebar:
    st.markdown('<h2 class="sidebar-title">💬 Conversaciones</h2>', unsafe_allow_html=True)
    # Add "New Chat" button at the top
    if st.button("Nueva Conversación"):
        new_session_id = str(uuid.uuid4())
        
        #Update session state
        st.session_state.session_id = new_session_id
        st.session_state.messages = []
        st.rerun()

    # Get all sessions and create buttons
    sessions = get_all_sessions()
    
    # Show divider if there are existing sessions
    if sessions:
        st.divider()
        st.subheader("Historial")
    
    # Create a button for each session
    for session in sessions:
        # Use columns to place chat button and delete button side by side
        col1, col2 = st.columns([4, 1])
        
        # Format the date
        date_str = session['created_at'].strftime("%Y-%m-%d %H:%M")
        preview = session['last_message'][:30] + "..." if len(session['last_message']) > 30 else session['last_message']
        button_label = f"{date_str}\n{preview}"
        
        # Highlight current session
        is_current = session['session_id'] == st.session_state.session_id
        
        # Chat button in first column
        with col1:
            if st.button(
                button_label,
                key=f"chat_{session['session_id']}",
                use_container_width=True,
                type="primary" if is_current else "secondary"
            ):
                st.session_state.session_id = session['session_id']
                st.session_state.messages = load_chat_history(session['session_id'])
                st.rerun()
        
        # Delete button in second column
        with col2:
            if st.button("🗑️", key=f"delete_{session['session_id']}", type="secondary"):
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            DELETE FROM chat_messages 
                            WHERE session_id = %s
                        """, (session['session_id'],))
                        conn.commit()
                        cur.execute("""
                            DELETE FROM ai_memory 
                            WHERE user_id = %s
                        """, (session['session_id'],))
                        conn.commit()                
                        cur.execute("""
                            DELETE FROM user_cart 
                            WHERE user_id = %s
                        """, (session['session_id'],))
                        conn.commit()                

                    # If we're deleting the current session, create a new one
                if session['session_id'] == st.session_state.session_id:
                    st.session_state.session_id = str(uuid.uuid4())
                    st.session_state.messages = []
                st.rerun()

    # Add delete all button at the bottom
    if st.button("Borrar Todo el Historial", type="secondary"):
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM chat_messages")
                cur.execute("DELETE FROM ai_memory")
                cur.execute("DELETE FROM user_cart")
                conn.commit()
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()

# Main chat interface
user_query = st.chat_input('En que te puedo ayudar?')

# Display chat messages
for msg in st.session_state.messages:
    if isinstance(msg, AIMessage):
        st.chat_message("assistant", avatar=BOT_AVATAR).write(msg.content)
    elif isinstance(msg, HumanMessage):
        st.chat_message("user", avatar=USER_AVATAR).write(msg.content)

# Handle user input
if user_query:
    # Save user message
    st.chat_message("user", avatar=USER_AVATAR).write(user_query)

    save_message(st.session_state.session_id, "user", user_query)
    st.session_state.messages.append(HumanMessage(content=user_query))


    st.session_state.my_cart = load_cart(st.session_state.session_id)
    st.session_state.user_preferences = load_preferences(st.session_state.session_id)
    st.session_state.summaries = load_summaries(st.session_state.session_id)
    st.session_state.old_carts = load_old_carts(st.session_state.session_id)

    state = {
        "messages": st.session_state.messages,
        "cart": st.session_state.my_cart,
        "user_id": st.session_state.session_id,
        "preferences": st.session_state.user_preferences,
        "summaries": st.session_state.summaries,
        "old_carts": st.session_state.old_carts
    }

    placeholder = st.container()
    response = asyncio.run(invoke_our_graph(state, BOT_AVATAR))

    # Save assistant message
    save_message(
        st.session_state.session_id,
        "assistant",
        response["messages"].content
    )
    st.session_state.messages.append(response["messages"])

    st.session_state.my_cart = response["cart"]
    from db import save_cart, save_preferences
    save_cart(st.session_state.session_id, st.session_state.my_cart)

    st.session_state.user_preferences = response["preferences"]
    save_preferences(st.session_state.session_id, st.session_state.user_preferences)