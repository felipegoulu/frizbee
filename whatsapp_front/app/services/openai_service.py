
import os
import sys
import asyncio  # Import asyncio

from langchain_core.messages import AIMessage, HumanMessage
from backend.graph import graph_runnable

from backend.db import load_cart, load_preferences, load_summaries, load_old_carts, load_chat_history, load_key, save_preferences, save_cart, save_message


async def invoke_our_graph(state): 
    final_response = {"messages": [], "cart": [], "preferences": ""}

    response = await graph_runnable.ainvoke(state)
    
    # Since we're not streaming anymore, we can directly process the response
    if "messages" in response and "preferences" in response: 
        final_response["messages"] = response["messages"]
        final_response["preferences"] = response["preferences"]
    return final_response

def generate_response(message_body, wa_id, msg_id):
    # aca llega el ultimo mensaje solo

    save_message(wa_id, "user", message_body, msg_id)
    
    messages = load_chat_history(wa_id)
    messages.append(HumanMessage(content=message_body))

    user_preferences = load_preferences(wa_id)
    summaries = load_summaries(wa_id)
    old_carts = load_old_carts(wa_id)
    key = load_key(wa_id)

    # Run the assistant and get the new message
    state = {
        "messages": messages,
        "user_id": wa_id,
        "preferences": user_preferences,
        "summaries": summaries,
        "old_carts": old_carts,
        "key": key
    }

    response = asyncio.run(invoke_our_graph(state))
    new_message = response["messages"][-1].content

    save_message(wa_id, "assistant", new_message, '')

    user_preferences = response["preferences"]
    save_preferences(wa_id, user_preferences)

    # key = state["key"]

    return new_message


