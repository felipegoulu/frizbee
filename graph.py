from typing import Annotated, TypedDict, Literal

from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool, StructuredTool
from langgraph.graph import START, StateGraph
from langgraph.graph.message import AnyMessage, add_messages
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, ToolMessage, SystemMessage

from tools.tool import product_lookup_tool
from tools.jumbo_bot_api import make_list

# This is the default state same as "MessageState" TypedDict but allows us accessibility to custom keys
class GraphsState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    # Custom keys for additional data can be added here such as - conversation_id: str

graph = StateGraph(GraphsState)

# Creo el nodo tool

# List of tools that will be accessible to the graph via the ToolNode
tools = [product_lookup_tool, make_list]

tools_by_name = {tool.name: tool for tool in tools}

model = ChatOpenAI(model="gpt-4o-mini")
llm = model.bind_tools(tools)

import asyncio

async def product_lookup_tool(state: dict):
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


from threading import Thread

def jumbo_bot(state: dict):
    tool_call = state["messages"][-1].tool_calls[0]
    tool = tools_by_name[tool_call["name"]]
    
    # Ejecutar en un thread separado
    Thread(target=tool.invoke, args=(tool_call["args"],), daemon=True).start()

    return {"messages": [ToolMessage(content="Procesando tu pedido...", tool_call_id=tool_call["id"], type="tool")]}

'''
def jumbo_bot(state: dict):
    result = [] 
    tool_call = state["messages"][-1].tool_calls[0]
    tool = tools_by_name[tool_call["name"]]
    observation = tool.invoke(tool_call["args"])
    result.append(ToolMessage(content=observation, tool_call_id = tool_call["id"], type="tool"))
    return {"messages": result}
'''
def determine_tool_node(state: GraphsState) -> Literal["product_lookup", "jumbo_bot", "__end__"]:
    if not state["messages"][-1].tool_calls:
        return "__end__"
    
    tool_name = state["messages"][-1].tool_calls[0]["name"]
    
    if tool_name == "product_lookup_tool":
        return "product_lookup"
    elif tool_name == "make_list":
        return "jumbo_bot"  # Continue to tool execution
    return "__end__"  # End the conversation if no tool is needed

# Core invocation of the model
def _call_model(state: GraphsState):
    system_prompt = SystemMessage('''
        Eres un asistente de IA que ayuda a los usuarios a hacer compras online en el supermercado Jumbo. 

        Principalmente, ayudarás al usuario en:

        Recetas de comida: El usuario puede pedir los ingredientes para una receta específica. Debes buscar los ingredientes en la receta y luego encontrar cada ingrediente en la base de datos del supermercado usando la herramienta.
        Recomendaciones de alimentos: El usuario puede pedir una recomendación. Deberías pensar en una recomendación y luego verificar en la base de datos del supermercado si está disponible.
        Búsqueda normal: El usuario puede pedir un producto específico, y debes recuperar los productos más similares de la base de datos usando la herramienta.

        Para usar la herramienta, necesitas enviar los productos que debes buscar en la base de datos. La herramienta recuperará esos productos. Busca un producto a la vez. Si la herramienta no recupera la información necesaria, intenta de nuevo hasta que obtengas el producto correcto; nunca inventes productos.

        Si la herramienta no recupera ningún producto para el que estás buscando, simplemente responde: Producto X no encontrado.

        Solo busca sal si el usuario la pide específicamente.

        Al devolver la respuesta, recuerda que el usuario es un amante de la comida, y la respuesta debe ayudar al usuario a entender el porqué del producto. Eres un experto en gastronomía y debes describir las elecciones al usuario de una manera descriptiva.                                  

        NO muestres las IMAGENES

        Cuando el usario pide un producto, responde como maximo 4 opciones para ese producto

        Si el usuario dice: "Hace la compra", debes utilizar la tool llamada jumbo_bot y poner como input el link de los productos que quieres añadir al carrito. (enviar como lista)                                  

          ''')

    conversation = [system_prompt] + state["messages"]
    response = llm.invoke(conversation)
    return {"messages": [response]}  # add the response to the messages using LangGraph reducer paradigm

# Define the structure (nodes and directional edges between nodes) of the graph
graph.add_edge(START, "modelNode")
graph.add_node("product_lookup", product_lookup_tool)
graph.add_node("jumbo_bot", jumbo_bot)
graph.add_node("modelNode", _call_model)

# Add conditional logic to determine the next step based on the state (to continue or to end)
graph.add_conditional_edges(
    "modelNode",
    determine_tool_node,  # This function will decide the flow of execution
)

graph.add_edge("product_lookup", "modelNode")
graph.add_edge("jumbo_bot", "modelNode")

# Compile the state graph into a runnable object
graph_runnable = graph.compile()