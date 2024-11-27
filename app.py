from dotenv import load_dotenv

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage
import asyncio

import nltk
@st.cache_resource  # This decorator ensures the download happens only once
def download_nltk_resources():
    nltk.download('punkt_tab')
   
download_nltk_resources()

from astream_events_handler import invoke_our_graph   # Utility function to handle events from astream_events from graph
import os
from dotenv import load_dotenv
load_dotenv()
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

USER_AVATAR = "🧑🏻"
BOT_AVATAR = "🤖"

# Capture user input from chat input
user_query = st.chat_input('En que te puedo ayudar?')

# Initialize chat messages in session state
if "messages" not in st.session_state:
    st.session_state.messages = []  # Reset the chat history

if "my_cart" not in st.session_state:
    st.session_state.my_cart = []

st.markdown("""
    <style>
    .cart-item {
        padding: 12px;
        margin: 8px 0;
        background-color: #f8f9fa;
        border-radius: 8px;
        border-left: 4px solid #007bff;
    }
    .total-section {
        padding: 15px;
        margin-top: 20px;
        background-color: #e9ecef;
        border-radius: 8px;
        font-size: 1.1em;
    }
    .product-link {
        color: #007bff;
        text-decoration: none;
        font-weight: bold;
    }
    .product-link:hover {
        text-decoration: underline;
        color: #0056b3;
    }
    </style>
""", unsafe_allow_html=True)

# Sidebar with a button to delete chat history
with st.sidebar:
    #st.title('💬 Asistente Frizbee')
    #st.markdown('📖 Frizbee tiene todo el catalogo de Jumbo. Preguntale que quieres comprar y el te arma la lista y luego lo compra automaticamente!')
    if st.button("Borrar Historial"):
        st.session_state.messages = []

    st.markdown("### 🛒 Shopping Cart")
    st.markdown("---")


#from initial_questions import show_initial_questions
# Cuando quieras mostrar la pregunta inicial:
#st.session_state.user_choices = show_initial_questions(BOT_AVATAR)
#print(st.session_state.user_choices)

# Loop through all messages in the session state and render them as a chat on every st.refresh mech
for msg in st.session_state.messages:
    if isinstance(msg, AIMessage):
        st.chat_message("assistant", avatar=BOT_AVATAR).write(msg.content)
    elif isinstance(msg, HumanMessage):
        st.chat_message("user", avatar= USER_AVATAR).write(msg.content)

# Handle user input if provided

if  user_query:
    state = {
        "messages": st.session_state.messages,
        "cart": st.session_state.my_cart,
    }

    placeholder = st.container()
    response = asyncio.run(invoke_our_graph(state, BOT_AVATAR))

    st.session_state.messages.append(response["messages"])
    st.session_state.my_cart = response["cart"]
    with st.sidebar:
        st.sidebar.empty()    


        total = 0
        for i in range(len(st.session_state.my_cart)):
            nombre = st.session_state.my_cart[i]["name"] 
            cantidad = st.session_state.my_cart[i]["quantity"] 
            precio = st.session_state.my_cart[i]["price"] 
            link = st.session_state.my_cart[i]["link"] 
            #precio_double = float(precio.strip("$"))
            #total += precio_double

            st.markdown(f"""
                <div class="cart-item">
                    <div style="display: flex; justify-content: space-between;">
                        <a href={link} class="product-link">{nombre}</a>
                        <span>{precio}</span>
                    </div>
                    <div style="color: #666; font-size: 0.9em;">Qty: {cantidad}</div>
                </div>
            """, unsafe_allow_html=True)

        #st.markdown(f"""
        #    <div class="total-section">
        #        <div style="display: flex; justify-content: space-between;">
        #            <strong>Total</strong>
        #            <strong>{total}</strong>
        #        </div>
        #    </div>
        #""", unsafe_allow_html=True)