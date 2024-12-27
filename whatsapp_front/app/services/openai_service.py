
import os
import sys
import asyncio  # Import asyncio

from langchain_core.messages import AIMessage, HumanMessage
from backend.graph import graph_runnable

from backend.db import load_cart, load_preferences, load_summaries, load_old_carts, load_chat_history, save_preferences, save_cart, save_message


async def invoke_our_graph(state): 
    final_response = {"messages": [], "cart": [], "preferences": ""}

    # for event in graph_runnable.stream_events(state, version="v2"):
    #     kind = event["event"]  
    #     if kind == 'on_chain_end':
    #         response = event['data']["output"]
    #         if "messages" in response and "cart" in response and "preferences" in response:
    #             final_response["cart"] = response["cart"]
    #             final_response["preferences"] = response["preferences"]
    #             final_response["messages"] = response["messages"]
    # # End of Selection
    # Replace stream_events with invoke
    response = await graph_runnable.ainvoke(state)
    
    # Since we're not streaming anymore, we can directly process the response
    if "messages" in response and "cart" in response and "preferences" in response:
        final_response["cart"] = response["cart"]
        final_response["preferences"] = response["preferences"]
        final_response["messages"] = response["messages"]
    return final_response

def generate_response(message_body, wa_id, name):
    # aca llega el ultimo mensaje solo

    save_message(wa_id, "user", message_body)
    
    messages = load_chat_history(wa_id)
    messages.append(HumanMessage(content=message_body))

    my_cart = load_cart(wa_id)
    user_preferences = load_preferences(wa_id)
    summaries = load_summaries(wa_id)
    old_carts = load_old_carts(wa_id)


    # Run the assistant and get the new message
    state = {
        "messages": messages,
        "cart": my_cart,
        "user_id": wa_id,
        "preferences": user_preferences,
        "summaries": summaries,
        "old_carts": old_carts
    }

    response = asyncio.run(invoke_our_graph(state))
    new_message = response["messages"][-1].content

    save_message(wa_id, "assistant", new_message)

    my_cart = response["cart"]
    save_cart(wa_id, my_cart)

    user_preferences = response["preferences"]
    save_preferences(wa_id, user_preferences)

    return new_message


