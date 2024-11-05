from dotenv import load_dotenv

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage
import asyncio

from astream_events_handler import invoke_our_graph   # Utility function to handle events from astream_events from graph

load_dotenv()

USER_AVATAR = "👨🏼‍🏭"
BOT_AVATAR = "🤖"

# Capture user input from chat input
user_query = st.chat_input('En que te puedo ayudar?')

# Initialize chat messages in session state
if "messages" not in st.session_state:
    st.session_state.messages = []  # Reset the chat history

# Sidebar with a button to delete chat history
with st.sidebar:
    st.title('💬 Asistente Frizbee')
    st.markdown('📖 Frizbee tiene todo el catalogo de Jumbo. Preguntale que quieres comprar y el te arma la lista y luego lo compra automaticamente!')
    if st.button("Borrar Historial"):
        st.session_state.messages = []

# Loop through all messages in the session state and render them as a chat on every st.refresh mech
for msg in st.session_state.messages:
    if isinstance(msg, AIMessage):
        st.chat_message("assistant", avatar=BOT_AVATAR).write(msg.content)
    elif isinstance(msg, HumanMessage):
        st.chat_message("user", avatar= USER_AVATAR).write(msg.content)

# Handle user input if provided
if user_query:
    st.session_state.messages.append(HumanMessage(content=user_query))
    st.chat_message("user", avatar = USER_AVATAR).write(user_query)

    with st.chat_message("assistant", avatar = BOT_AVATAR):
        placeholder = st.container()
        response = asyncio.run(invoke_our_graph(st.session_state.messages, placeholder))
        st.session_state.messages.append(AIMessage(response))
