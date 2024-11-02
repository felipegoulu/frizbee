from langchain_core.messages import AIMessage
import streamlit as st
from graph import graph_runnable

async def invoke_our_graph(st_messages, st_placeholder):
    container = st_placeholder  # Holds the dynamic UI components for Streamlit
    token_placeholder = container.empty()  # Used to display updates of tokens progressively
    final_text = ""  # Accumulates the text from the model's response
    async for event in graph_runnable.astream_events({"messages": st_messages}, version="v2"):
        kind = event["event"]  
        if kind == "on_chat_model_stream":
            addition = event["data"]["chunk"].content  
            final_text += addition  
            if addition:
                token_placeholder.write(final_text)  

    return final_text
