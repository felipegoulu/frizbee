from typing import Annotated, TypedDict, Literal, List
import json

from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool, StructuredTool
from langgraph.graph import START, StateGraph
from langgraph.graph.message import AnyMessage, add_messages
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, ToolMessage, SystemMessage, AIMessage

from tools.tool import product_lookup_tool

from contextlib import contextmanager
import psycopg2
from psycopg2.extras import RealDictCursor

import os
from dotenv import load_dotenv
load_dotenv()
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

os.environ["LANGSMITH_API_KEY"] = os.getenv("LANGCHAIN_API_KEY")
os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT")
os.environ["LANGCHAIN_TRACING_V2"] = os.getenv("LANGCHAIN_TRACING_V2")

class CartItem(TypedDict):
    name: str
    quantity: str
    price: str
    link: str

class GraphsState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    cart: List[CartItem]
    user_id: str
    preferences: str


graph = StateGraph(GraphsState)

@contextmanager
def get_db_connection():
    conn = None
    try:
        conn = psycopg2.connect(
            dbname=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            host=os.getenv('DB_HOST'),
            port=os.getenv('DB_PORT')
        )
        yield conn
    except psycopg2.Error as e:
        print(f"Database connection failed: {e}")
        raise
    finally:
        if conn is not None:
            conn.close()

@tool
async def save_to_memory(user_id: str, content: str, context: str):
    """
    Save important information about the user to AI's memory.
    Args:
        user_id: The user's ID
        content: The information to remember (what the user said or preference)
        context: Why this information is important or when it was mentioned
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO ai_memory 
                    (user_id, content, context)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (user_id, content, context))
                conn.commit()
                
        return f"Memorizado: {content} (Contexto: {context})"
    except Exception as e:
        return f"Error guardando en memoria: {str(e)}"

@tool
async def add_product(name, quantity, price, link):
    ''' Gets product name with price and quantity and adds them to the cart'''
    cart = {
        "name": name,
        "quantity": quantity,
        "price": price,
        "link": link
    }

    message = f"Added {name} to the cart"

    return message, cart

@tool
async def remove_product(name,cart):
    ''' Remove a product from the cart'''

    for i in range(len(cart)):
        if cart[i]["name"] == name:
            cart.pop(i)
        
    message = f"Removed {name} from the cart"

    return message, cart

@tool
async def change_quantity(name, new_quantity, cart):
    ''' Change the quantiy of a product inside the cart'''
    for i in range(len(cart)):
        if cart[i]["name"] == name:
            cart[i]["quantity"] = new_quantity
            message = f"Changed te queantity of {name} to {new_quantity}"
            return message, cart
    message = f"Product {name} not found in cart"
    return message, cart

# Shopping tools (main flow)
tools = [product_lookup_tool, add_product, remove_product, change_quantity]
tools_by_name = {tool.name: tool for tool in tools}

# Preferences tools
preferences_tools = [save_to_memory]
preferences_tools_by_name = {tool.name: tool for tool in preferences_tools}

model = ChatOpenAI(model="gpt-4o-mini")
llm = model.bind_tools(tools)

import asyncio

async def add_product(state: dict):
    result = []
    tasks = []

    print(f'''state[cart] : {state["cart"]}''')
    for tool_call in state["messages"][-1].tool_calls:
        tool=tools_by_name[tool_call["name"]]
        task= asyncio.create_task(tool.ainvoke(tool_call["args"]))
        print(tool_call["args"])
        tasks.append((task, tool_call["id"]))

    for task, tool_call_id in tasks:
        observation, cart = await task
        result.append(ToolMessage(content=observation, tool_call_id=tool_call_id, type='tool'))
        print(f"cart: {cart}")
        state["cart"].append(cart)

    return {"messages": result, "cart": state["cart"]}

async def change_quantity(state: dict):
    result = []
    tasks = []

    for tool_call in state["messages"][-1].tool_calls:
        tool=tools_by_name[tool_call["name"]]
        task= asyncio.create_task(tool.ainvoke(tool_call["args"]))
        tasks.append((task, tool_call["id"]))

    for task, tool_call_id in tasks:
        observation, cart = await task
        result.append(ToolMessage(content=observation, tool_call_id=tool_call_id, type='tool'))

    return {"messages": result, "cart": cart}


async def remove_product(state: dict):
    result = []
    tasks = []
    for tool_call in state["messages"][-1].tool_calls:
        tool=tools_by_name[tool_call["name"]]
        task= asyncio.create_task(tool.ainvoke(tool_call["args"]))
        tasks.append((task, tool_call["id"]))

    for task, tool_call_id in tasks:
        observation, cart = await task
        result.append(ToolMessage(content=observation, tool_call_id=tool_call_id, type='tool'))

    return {"messages": result, "cart": cart}

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

    return {"messages": result, "cart": state["cart"]}

async def save_memory(state: dict):
    """
    Node that handles save_to_memory tool calls during preferences collection
    """ 

    result = []
    tasks = []

    for tool_call in state["messages"][-1].tool_calls:
        tool = preferences_tools_by_name[tool_call["name"]]
        task = asyncio.create_task(tool.ainvoke(tool_call["args"]))
        tasks.append((task, tool_call["id"]))

    for task, tool_call_id in tasks:
        observation = await task
        result.append(ToolMessage(content=observation, tool_call_id=tool_call_id, type='tool'))

    return {"messages": result, "cart": state["cart"]}



def determine_tool_node(state: GraphsState) -> Literal["product_lookup", "add_product","remove_product","change_quantity", "__end__"]:
    if not state["messages"][-1].tool_calls:
        return "__end__"
    
    tool_name = state["messages"][-1].tool_calls[0]["name"]
    
    if tool_name == "product_lookup_tool":
        return "product_lookup"
    if tool_name == "add_product":
        return "add_product"
    if tool_name =="remove_product":
        return "remove_product"
    if tool_name =="change_quantity":
        return "change_quantity"
    else:
        return "__end__"  # End the conversation if no tool is needed


def determine_preferences_tool(state: GraphsState):
    """
    Determines next node in preferences flow: either save_memory or end
    """
    if not state["messages"][-1].tool_calls:
        return "__end__"
    
    tool_name = state["messages"][-1].tool_calls[0]["name"]
    return "save_memory" if tool_name == "save_to_memory" else "__end__"   

def determine_initial_node(state:GraphsState):
    """
    Use LLM to decide whether to go to add_preferences or shopping node based on the conversation history
    """
    system_prompt = SystemMessage(content="""
    Tu única función es decidir si el usuario necesita configurar preferencias o hacer compras.
    
    DEBES RESPONDER ÚNICAMENTE CON UNA DE ESTAS DOS PALABRAS:
    - "add_preferences"
    - "shopping"
    
    REGLAS:
    Responde "add" si:
    - Es una conversación nueva
    - El usuario quiere configurar preferencias
    - Menciona información personal nueva
    - Menciona restricciones o alergias
    - Falta información del usuario
    - Si el usuario dice que quiere hacer una compra, pero no hay informacion, deberias ir a add
    
    Responde "shopping" si:
    - Ya hay preferencias y quiere comprar
    - Pregunta por productos específicos
    - Quiere ver/modificar su carrito
    - Ya está comprando
    
    Si no sabes que responder, utiliza el mismo que utilizaste anteriormente.
    
    si el usuario no sabe que hacer, siempre debes ir al shopping asi el ai shopping le hace preguntas y lo asiste
    NO AGREGUES NINGÚN OTRO TEXTO O EXPLICACIÓN.
    RESPONDE ÚNICAMENTE CON UNA DE ESTAS DOS PALABRAS:
    - "shopping"
    - "add"

    """)

        # Create a simple model for decision (doesn't need tools)
    decision_model = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        max_tokens=1,   # Limitar la longitud de la respuesta
        presence_penalty=-2.0,  # Desalentar texto adicional
        frequency_penalty=-2.0  # Desalentar variaciones

    )

    recent_messages = state["messages"][-4:] if len(state["messages"]) > 4 else state["messages"]
    conversation = [system_prompt] + recent_messages
    response = decision_model.invoke(conversation)
    decision = response.content.lower()

    valid_responses = {"add", "shopping"}
    if decision not in valid_responses:
        print(f"WARNING: LLM returned invalid response: {decision}")
        # Por defecto, es más seguro empezar con preferencias
        return "modelNode"

    if decision == "shopping":
        decision = "modelNode"
    if decision =="add":
        decision = "add_preferences"
    return decision

def add_preferences(state: GraphsState):
    """
    Node that handles saving user preferences and manages preference-related conversation.
    Returns to shopping node once preferences are collected.
    """
    user_id = state["user_id"]
    system_prompt = SystemMessage(content=f'''
    Eres un asistente amable que ayuda a recolectar y guardar las preferencias del usuario.
    
    El user_id del usuario es {user_id}

    OBJETIVO:
    - Recolectar información relevante sobre preferencias de compra
    - Guardar cada preferencia importante usando la herramienta save_to_memory
    - Mantener una conversación natural y amigable
    
    INFORMACIÓN A RECOLECTAR:
    - Preferencias dietéticas (vegetariano, vegano, etc.)
    - Alergias o restricciones alimentarias
    - Tamaño de familia/cantidad usual de compras
    - Recetas habituales
    - Postres favoritos
    - desayuno habitual
    - Cualquier otra información relevante para compras
    
    IMPORTANTE:
    - Usa save_to_memory para guardar cada preferencia importante
    - Guarda el contexto de cada preferencia
    - Confirma la información con el usuario

                                  
    Debes preguntarle al usuario que quiere haciendo preguntas y dandole ejemplos, debes ser proactivo para obtener la informacion del usuario
    ''')

    preferences_model = ChatOpenAI(
        model = "gpt-4o-mini",
        temperature=0.7
    ).bind_tools([save_to_memory])

    conversation = [system_prompt] + state["messages"]
    response = preferences_model.invoke(conversation)

    return {"messages": [response], "cart": state["cart"]}


from prompts import get_shopping_assistant_prompt 
# Core invocation of the model
def _call_model(state: GraphsState):
    cart_info = f'''\nCarrito actual: {state["cart"]}'''
    user_id = state["user_id"]
    user_preferences = state["preferences"]
  
    prompt_content = get_shopping_assistant_prompt(
        user_preferences=user_preferences,
        user_id=user_id,
        cart_info=cart_info
    )
    system_prompt = SystemMessage(content=prompt_content)
    conversation = [system_prompt] + state["messages"] 
    response = llm.invoke(conversation)

    # If it has tool_calls, return the response directly. I need all the answer because it has the tool call name.
    if hasattr(response, 'tool_calls') and response.tool_calls:
        return {
            "messages": [response],  # Return the original message with tool_calls
            "cart": state["cart"]
        }
    
    else:
        return {"messages": [AIMessage(content=response.content)], "cart": state["cart"]}

# Define the structure (nodes and directional edges between nodes) of the graph
#graph.add_edge(START, "")
graph.add_node("product_lookup", product_lookup_tool)
graph.add_node("modelNode", _call_model)
graph.add_node("add_product", add_product)
graph.add_node("remove_product", remove_product)
graph.add_node("change_quantity", change_quantity)
graph.add_node("save_memory", save_memory)
graph.add_node("add_preferences", add_preferences)

# Add conditional logic to determine the next step based on the state (to continue or to end)
graph.add_conditional_edges(
    START,
    determine_initial_node,  # This function will decide the flow of execution
)

graph.add_conditional_edges(
    "modelNode",
    determine_tool_node,  # This function will decide the flow of execution
)

graph.add_conditional_edges(
    "add_preferences",
    determine_preferences_tool
)
graph.add_edge("product_lookup", "modelNode")
graph.add_edge("add_product", "modelNode")
graph.add_edge("remove_product", "modelNode")
graph.add_edge("change_quantity", "modelNode")
graph.add_edge("save_memory", "add_preferences")
# Compile the state graph into a runnable object
graph_runnable = graph.compile()