from typing import Annotated, TypedDict, Literal, List
import json

from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool, StructuredTool
from langgraph.graph import START, END, StateGraph
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
    summaries: str
    old_carts: str

graph = StateGraph(GraphsState)


@tool
async def save_to_memory(user_id: str, content: str, context: str):
    """
    Save important information about the user to AI's memory.
    Args:
        user_id: The user's ID (must be a valid UUID)
        content: The information to remember (what the user said or preference)
        context: Why this information is important or when it was mentioned
    """
    try:
        preference = f"{content}|{context}"        
        return preference

    except Exception as e:
        return f"ERROR|{str(e)}"

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
async def remove_product(name):
    ''' Remove a product from the cart'''
    message = f"Removed {name} from the cart"
    return message, name

@tool
async def change_quantity(name, new_quantity):
    ''' Change the quantiy of a product inside the cart'''
    message = f"Changed the quantity of {name} to {new_quantity}"
    return message, {"name": name, "quantity": new_quantity}   

# Shopping tools (main flow)
tools = [product_lookup_tool, add_product, remove_product, change_quantity]
tools_by_name = {tool.name: tool for tool in tools}

# Preferences tools
preferences_tools = [save_to_memory]
preferences_tools_by_name = {tool.name: tool for tool in preferences_tools}

model = ChatOpenAI(model="gpt-4o-mini")
llm = model.bind_tools(tools)

import asyncio

async def handle_shopping_tools(state: dict):
    result = []
    tasks = []
    current_cart = state["cart"].copy()

    # Crear todas las tareas primero para ejecución paralela
    for tool_call in state["messages"][-1].tool_calls:
        tool_name = tool_call["name"]
        tool = tools_by_name[tool_name]
        task = asyncio.create_task(tool.ainvoke(tool_call["args"]))
        tasks.append((task, tool_call["id"], tool_name))

    # Esperar todas las tareas y procesar resultados
    for task, tool_call_id, tool_name in tasks:
        if tool_name == "product_lookup_tool":
            observation = await task
            result.append(ToolMessage(content=observation, tool_call_id=tool_call_id, type='tool'))
        
        elif tool_name == "add_product":
            message, cart_item = await task
            result.append(ToolMessage(content=message, tool_call_id=tool_call_id, type='tool'))
            current_cart.append(cart_item)
        
        elif tool_name == "remove_product":
            message, product_name = await task
            current_cart = [item for item in current_cart if item["name"] != product_name]
            result.append(ToolMessage(content=message, tool_call_id=tool_call_id, type='tool'))


        elif tool_name == "change_quantity":
            message, change_info = await task
            for item in current_cart:
                if item["name"] == change_info["name"]:
                    item["quantity"] = change_info["quantity"]
            result.append(ToolMessage(content=message,  tool_call_id=tool_call_id, type='tool'))

    return {"messages": result, "cart": current_cart}

async def save_memory(state: dict):
    """
    Node that handles save_to_memory tool calls during preferences collection
    """ 

    result = []
    tasks = []
    preferences = state["preferences"]

    for tool_call in state["messages"][-1].tool_calls:
        tool = preferences_tools_by_name[tool_call["name"]]
        task = asyncio.create_task(tool.ainvoke(tool_call["args"]))
        tasks.append((task, tool_call["id"]))

    for task, tool_call_id in tasks:
        observation = await task
        result.append(ToolMessage(content=observation, tool_call_id=tool_call_id, type='tool'))

        # Procesar respuesta estructurada
        if "|" in observation and not observation.startswith("ERROR"):
            content, context = observation.split("|")
            new_preference = f"- {content} ({context})"
            preferences = f"{preferences}\n{new_preference}"


    return {
        "messages": result, 
        "cart": state["cart"],
        "preferences": preferences  # Asegúrate de que esto esté presente
    }

def determine_tool_node(state: GraphsState) -> Literal["handle_shopping_tools", "__end__"]:
    if not state["messages"][-1].tool_calls:
        return "__end__"
    
    tool_name = state["messages"][-1].tool_calls[0]["name"]
    
    shopping_tools = {
        "product_lookup_tool",
        "add_product",
        "remove_product",
        "change_quantity"
    }

    if tool_name in shopping_tools: 
        return "handle_shopping_tools"
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
    
    DEBES RESPONDER ÚNICAMENTE CON UNA DE ESTAS PALABRAS:
    - "long" (preferencias a largo plazo)
    - "shopping" (proceso de compra)
    - "end" (finalizar compra)
    
    REGLAS:
    Responde "long" si:
    - Es una conversación nueva
    - El usuario quiere configurar preferencias
    - Menciona información personal nueva
    - Menciona restricciones o alergias
    - Falta información del usuario
    - SI el usuario quiere agregar productos al carrito, RESPONDE shopping SIEMPRE!
    
    Responde "shopping" si:
    - El usuario menciona productos específicos
    - Solicita buscar o agregar productos al carrito
    - Quiere modificar cantidades en el carrito
    - Ya está en proceso activo de compra
    - El usuario necesita ayuda o sugerencias de compra  
    - el usuario quiere agregar, borrar modificar productos de su carrito

    Response "end" si:
    - El usuario dice explícitamente que quiere completar/finalizar la compra
    - El usuario quiere pagar
    - El usuario dice que ya terminó de comprar                              
    - Si la respuesta es "end", la compra se compra, e inmediadamente el usuario hace el pago.
    
    Si no sabes que responder, utiliza el mismo que utilizaste anteriormente.
    
    si el usuario no sabe que hacer, siempre debes ir al shopping asi el ai shopping le hace preguntas y lo asiste
    NO AGREGUES NINGÚN OTRO TEXTO O EXPLICACIÓN.
    RESPONDE ÚNICAMENTE CON UNA DE ESTAS PALABRAS:
    - "shopping"
    - "long"
    - "end"

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

    valid_responses = {"long", "shopping", "end"}
    decision = None

    while decision not in valid_responses:
        response = decision_model.invoke(conversation)
        decision = response.content.lower()

    if decision == "shopping":
        return "modelNode"
    if decision =="long":
        return "add_preferences"
    if decision == "end":
        return "create_summary"

def add_preferences(state: GraphsState):
    """
    Node that handles saving user preferences and manages preference-related conversation.
    Returns to shopping node once preferences are collected.
    """
    user_id = state["user_id"]
    system_prompt = SystemMessage(content=f'''
    Eres uno de los dos asistentes AI que trabajan juntos en frizbee para ayudar en el proceso de compras en el supermercado jumbo.
    Tu única función es recolectar y guardar las preferencias del usuario de manera proactiva. No debes realizar ninguna otra tarea.

    El user_id del usuario es {user_id}

    OBJETIVO:
    - Explicarle al usuario que es frizbee
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
    - Sé proactivo: haz preguntas al usuario para obtener la información necesaria

    Debes preguntarle al usuario que quiere haciendo preguntas y dandole ejemplos, debes ser proactivo para obtener la informacion del usuario

    Una vez que terminas de recolectar las preferencias, debes preguntale al usuario sobre el tipo de compra que desea hacer:
      * "¿Qué tipo de compra te gustaría hacer hoy? Por ejemplo:
         - ¿Compra semanal completa?
         - ¿Ingredientes para alguna receta específica?
         - ¿Productos básicos?
         - ¿Algo específico que necesites?"

    ''')

    preferences_model = ChatOpenAI(
        model = "gpt-4o-mini",
        temperature=0.7
    ).bind_tools([save_to_memory])

    conversation = [system_prompt] + state["messages"]
    response = preferences_model.invoke(conversation)

    return {"messages": [response], "cart": state["cart"], "preferences": state["preferences"]}

from prompts import get_shopping_assistant_prompt 

# Core invocation of the model
def _call_model(state: GraphsState):
    cart_info = f'''\nCarrito actual: {state["cart"]}'''
    user_id = state["user_id"]
    user_preferences = state["preferences"]
    summaries= state["summaries"]
    old_carts= state["old_carts"]

    prompt_content = get_shopping_assistant_prompt(
        user_preferences=user_preferences,
        user_id=user_id,
        cart_info=cart_info,
        summaries=summaries,
        old_carts=old_carts,
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

def create_summary_node(state: GraphsState):
    """Node that handles completing the purchase"""

    from db import complete_cart, change_messages_status
    complete_cart(state["user_id"])
    make_summary(state["user_id"]) #el summary lo hago con los en proceso, y luego los cambio a completado
    change_messages_status(state["user_id"]) # con esto pongo status en completado.

    return {
            "messages": [''],
    }

def complete_purchase(state: GraphsState):
    model = ChatOpenAI(
        model = "gpt-4o-mini",
        streaming=True
    )

    system_message = SystemMessage(content="""
    La compra se ha completado con éxito. 
    Genera un mensaje amable agradeciendo al usuario por su compra y despidiéndote.
                                   """)

    response = model.invoke([system_message])

    return {
            "messages": [response],
            "cart": []  # Clear the cart after purchase
    }


def make_summary(user_id):
    """
    Retrieve user data from the database and generate a summary using AI.
    Args:
        user_id: The user's ID
    Returns:
        A summary of the user's data en la tabla ai_memory
    """
    from db import load_messages_en_proceso, add_summary_db
    messages = load_messages_en_proceso(user_id)

    model = ChatOpenAI(
        model = "gpt-4o-mini",
        streaming=False
    )

    system_message = SystemMessage(content=f"""
    Analiza la siguiente conversación entre un usuario y el asistente de compras de Jumbo:
    Extrae ÚNICAMENTE las preferencias del usuario en formato bullet points.

    Conversación:
    {messages}

    REGLAS:
    - Un guión por preferencia
    - Solo incluir preferencias alimenticias, de compra o restricciones
    - Ser conciso y directo
    - No incluir explicaciones ni texto adicional
    - No incluir recomendaciones
    
    Formato de respuesta:
    - preferencia 1
    - preferencia 2
    - etc.
                                   """)

    response = model.invoke([system_message])         
    summary_content = response.content
    summary_content = str(response.content).strip()


    add_summary_db(user_id, summary_content) # añade el sumary a la base de datos

# Define the structure (nodes and directional edges between nodes) of the graph
#graph.add_edge(START, "")
graph.add_node("modelNode", _call_model)
graph.add_node("handle_shopping_tools", handle_shopping_tools)
graph.add_node("save_memory", save_memory)
graph.add_node("add_preferences", add_preferences)
graph.add_node("create_summary", create_summary_node)
graph.add_node("complete_purchase", complete_purchase)

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

graph.add_edge("handle_shopping_tools", "modelNode")
graph.add_edge("save_memory", "add_preferences")
graph.add_edge("create_summary", "complete_purchase")
graph.add_edge("complete_purchase", END)
# Compile the state graph into a runnable object
graph_runnable = graph.compile()