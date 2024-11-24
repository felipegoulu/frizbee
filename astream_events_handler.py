from langchain_core.messages import AIMessage
import streamlit as st
from graph import graph_runnable

async def invoke_our_graph(state, BOT_AVATAR): 
    final_text = ""  # Accumulates the text from the model's response
    final_response = {"messages": [], "cart": []}
    with st.chat_message("assistant", avatar=BOT_AVATAR):
        chat_container = st.container()
    async for event in graph_runnable.astream_events(state, version="v2"):
        kind = event["event"]  
        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"].content  
            final_text += chunk  
            
            chat_container = chat_container.empty()
            chat_container.write(final_text)  

        if kind == 'on_chain_end':
            response = event['data']["output"]
            if "messages" in response and "cart" in response:
                # for cart:
                final_response["cart"] = response["cart"]
                # for AI message:
                messages = response["messages"]
                for msg in messages:
                    if isinstance(msg, AIMessage):
                        final_response["messages"] = msg        

    return final_response
