from langchain_core.messages import AIMessage
import streamlit as st
from graph import graph_runnable

async def invoke_our_graph(state, BOT_AVATAR): 
    final_text = ""  # Accumulates the text from the model's response
    final_response = {"messages": [], "cart": [], "preferences": ""}
    chunk_count = 0

    with st.chat_message("assistant", avatar=BOT_AVATAR):
        chat_container = st.container()

    async for event in graph_runnable.astream_events(state, version="v2"):
        #if "parent_ids" in event:
        #    continue
        kind = event["event"]  
        if kind == "on_chat_model_stream":

            chunk = event["data"]["chunk"].content  

            if event.get("metadata", {}).get("langgraph_node") in ["create_summary", "__start__"]:
                continue

            final_text += chunk  
            chat_container = chat_container.empty()
            chat_container.write(final_text)  

        if kind == 'on_chain_end':
            response = event['data']["output"]
            if "messages" in response and "cart" in response and "preferences" in response:
                # for cart:
                final_response["cart"] = response["cart"]
                # for preferences
                final_response["preferences"] = response["preferences"]
                # for AI message:
                messages = response["messages"]
                for msg in messages:
                    if isinstance(msg, AIMessage):
                        final_response["messages"] = msg        

    return final_response
