from typing import Annotated, TypedDict, Literal

from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool, StructuredTool
from langgraph.graph import START, StateGraph
from langgraph.graph.message import AnyMessage, add_messages
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, ToolMessage, SystemMessage

from tools.tool import product_lookup_tool

# This is the default state same as "MessageState" TypedDict but allows us accessibility to custom keys
class GraphsState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    # Custom keys for additional data can be added here such as - conversation_id: str

graph = StateGraph(GraphsState)

# Creo el nodo tool

# List of tools that will be accessible to the graph via the ToolNode
tools = [product_lookup_tool]

tools_by_name = {tool.name: tool for tool in tools}

model = ChatOpenAI(model="gpt-4o-mini")
llm = model.bind_tools(tools)

import asyncio

async def tool_node(state: dict):
    result = []

    # Create a list of tasks for parallel execution
    tasks = []

    for tool_call in state["messages"][-1].tool_calls:
        # Get the tool from the dictionary
        tool = tools_by_name[tool_call["name"]]
        # Create an async task for each tool invocation
        task = asyncio.create_task(tool.ainvoke(tool_call["args"]))
        # Append the task along with the tool_call_id for later use
        tasks.append((task, tool_call["id"]))

    # Wait for all tasks to complete (parallel execution)
    for task, tool_call_id in tasks:
        observation = await task
        # Collect the results as ToolMessage objects
        result.append(ToolMessage(content=observation, tool_call_id=tool_call_id, type='tool'))

    return {"messages": result}

def should_continue(state: GraphsState) -> Literal["tools", "__end__"]:
    messages = state["messages"]
    last_message = messages[-1]
    if last_message.tool_calls:  # Check if the last message has any tool calls
        return "tools"  # Continue to tool execution
    return "__end__"  # End the conversation if no tool is needed

# Core invocation of the model
def _call_model(state: GraphsState):
    system_prompt = SystemMessage('''
    You are an AI assistant that helps users when looking for products to buy in a supermarket delivery app. Never ask back to the user, always answer with the info the user gives you.
    
    For the most part, you are going to help user with:
    1. food recipes: User might ask for ingredients for a given recipie, and you have to look for the ingredients in the recipie and then retrieve every ingredient in the supermarket database with the tool.
    2. food recommendations: The user might ask for a recommendation. You should think about a recommendation and then look for it in the supermarket database to see if it is available.
    3. Normal search: The user might ask for a certain product and you should retrieve the most similar products from the database with the tool.

    To use the tool, you need to send the products you need to look for in the database. The tool will retrieve those products.Look for one product at a time. If the tool doesnt retrieve the necesary info try again until you get it right, never invent products.

    When using the tool, say: look for ...
    For example: look for fresh tomatoes, look for frozen fruits, look for fresh steak, look for bacon, etc. Say if you want fresh/frozen (if it corresponds). 
    If you cannot find a product in the database, search for substitutes (example: if you cannot find panceta, use bacon)
    
    The product retrieved from the tool should perfectly match the product you are looking for. For example, if you want a tomato and the tool retrieves Carrots, Tomatoes & Broccoli Snack Tray, it is wrong and you should look again for the product. Never accept a product that doesnt match what you are looking for.

    NOTE: Always retrieve products that are in the product database. 

    If the tool didnt retrieve any product for the product you are looking for, just answer: Product X not found.

    When looking for multiple products, make the tool calls at the beggining.

    Pick the products you want from the tool response, and send it to the next node without changing the format. 
    
    Never repeat the same answer more than once!

    Only look for salt if the user asks for salt.

    When returning the answer, remember that the user is a foodie, and the answer should help the user understand the why of the product. You are a food expert and have to describe the choices to the user in a desctriptive manner.
          ''')

    conversation = [system_prompt] + state["messages"]
    response = llm.invoke(conversation)
    return {"messages": [response]}  # add the response to the messages using LangGraph reducer paradigm

# Define the structure (nodes and directional edges between nodes) of the graph
graph.add_edge(START, "modelNode")
graph.add_node("tools", tool_node)
graph.add_node("modelNode", _call_model)

# Add conditional logic to determine the next step based on the state (to continue or to end)
graph.add_conditional_edges(
    "modelNode",
    should_continue,  # This function will decide the flow of execution
)
graph.add_edge("tools", "modelNode")

# Compile the state graph into a runnable object
graph_runnable = graph.compile()