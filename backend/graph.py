from typing import Annotated, TypedDict, Literal, List
import json

from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool, StructuredTool
from langgraph.graph import START, END, StateGraph
from langgraph.graph.message import AnyMessage, add_messages
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, ToolMessage, SystemMessage, AIMessage

from backend.tools.tool import product_lookup_tool

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


class GraphsState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    user_id: str
    preferences: str
    summaries: str
    old_carts: str
    key: str

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

# Shopping tools (main flow)
tools = [product_lookup_tool]
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

    # Crear todas las tareas primero para ejecución paralela
    for tool_call in state["messages"][-1].tool_calls:
        tool_name = tool_call["name"]
        tool = tools_by_name[tool_name]
        task = asyncio.create_task(tool.ainvoke(tool_call["args"]))
        tasks.append((task, tool_call["id"], tool_name))

    # Esperar todas las tareas y procesar resultados
    for task, tool_call_id, tool_name in tasks:
        observation = await task
        result.append(ToolMessage(content=observation, tool_call_id=tool_call_id, type='tool'))
   
    return {"messages": result}

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
        "preferences": preferences  
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
    input = state["messages"][-1]    
    input = input.content

    key = state["key"]
    key = key['key']
    print(key)
    print(input)
    if input != '' and input == key:
        return "create_summary"

    from backend.prompts import get_determine_initial_node_prompt

    old_carts = state["old_carts"]

    if old_carts:
        prompt = "prompt2"
    else:
        prompt = "prompt1"

    # prompt puede ser prompt1, prompt2, prompt3
    prompt_content= get_determine_initial_node_prompt(prompt)
    system_prompt = SystemMessage(content=prompt_content)

        # Create a simple model for decision (doesn't need tools)
    decision_model = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
    )

    recent_messages = state["messages"][-4:] if len(state["messages"]) > 4 else state["messages"]
    conversation = [system_prompt] + recent_messages

    decision = None

    from backend.prompts import get_function_call_prompt
    tools = get_function_call_prompt(prompt) 

    response = decision_model.invoke(
        conversation, 
        tools = tools,
        tool_choice={"type": "function", "function": {"name": "determine_next_node"}}  # Added tool_choice
        )

    # Extract the decision from the function call
    tool_calls = response.additional_kwargs.get('tool_calls', [])
    if tool_calls and len(tool_calls) > 0:
        function_args = tool_calls[0].get('function', {}).get('arguments', '{}')
        decision = json.loads(function_args).get('decision')
        print(f"decision: {decision}")
        if decision == "shopping":
            return "modelNode"
        if decision =="long":
            return "add_preferences"
        if decision == "end":
            return "create_key"

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

    return {"messages": [response], "preferences": state["preferences"]}

from backend.prompts import get_shopping_assistant_prompt 

# Core invocation of the model
def _call_model(state: GraphsState):
    user_id = state["user_id"]
    user_preferences = state["preferences"]
    summaries= state["summaries"]
    old_carts= state["old_carts"][-1]

    prompt_content = get_shopping_assistant_prompt(
        user_preferences=user_preferences,
        user_id=user_id,
        summaries=summaries,
        old_carts=old_carts,
    )
    system_prompt = SystemMessage(content=prompt_content)
    conversation = [system_prompt] + state["messages"][-20:] 
    response = llm.invoke(conversation)
    # If it has tool_calls, return the response directly. I need all the answer because it has the tool call name.
    if hasattr(response, 'tool_calls') and response.tool_calls:
        return {
            "messages": [response]  # Return the original message with tool_calls
        }
    
    else:
        return {"messages": [AIMessage(content=response.content)]}

def create_summary_node(state: GraphsState):
    """Node that handles completing the purchase"""

    from backend.db import complete_cart, change_messages_status
    complete_cart(state["user_id"])
    make_summary(state["user_id"]) #el summary lo hago con los en proceso, y luego los cambio a completado
    change_messages_status(state["user_id"]) # con esto pongo status en completado.

    return {
            "messages": [''],
    }

def complete_purchase(state: GraphsState):
    model = ChatOpenAI(
        model = "gpt-4o-mini",
        model_kwargs={"response_format": {"type": "json_object"}}
    )


    system_message= SystemMessage(content=f"""
    Genera el carrito de compras en formato JSON. 
    El JSON debe incluir los siguientes campos para cada producto: 
    SIMPRE PONER EL CARRITO
    - nombre
    - precio
    - link

    Ejemplo de formato JSON: 
    {{"carrito": [ 
        {{
            "nombre": "Producto 1",
            "precio": 10.99,
            "link": "http://ejemplo.com/producto1"
        }},
        {{
            "nombre": "Producto 2",
            "precio": 5.49,
            "link": "http://ejemplo.com/producto2"
        }}
        ]
    }}

    Genera la respuesta en formato json.

    """)

   # Invocar el modelo para obtener el carrito en formato JSON
    json_cart_response = model.invoke([system_message] + state["messages"][-20:])
    json_cart = json_cart_response.content  # Suponiendo que el contenido es el JSON generado

    import json
    json_cart = json.loads(json_cart)
    json_cart = json.dumps(json_cart)

    print(json_cart)

    from backend.db import save_cart
    save_cart(state["user_id"], json_cart)

    model = ChatOpenAI(
        model = "gpt-4o-mini"
    )
    system_message = SystemMessage(content="""
    La compra se ha completado con éxito. 
    Genera un mensaje amable agradeciendo al usuario por su compra y despidiéndote.
                                   """)

    response = model.invoke([system_message])

    from backend.db import update_key
    update_key(state["user_id"], "")

    return {
            "messages": [response]
    }


def make_summary(user_id):
    """
    Retrieve user data from the database and generate a summary using AI.
    Args:
        user_id: The user's ID
    Returns:
        A summary of the user's data en la tabla ai_memory
    """
    from backend.db import load_messages_en_proceso, add_summary_db
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

def create_key(state: GraphsState):
    model = ChatOpenAI(
        model = "gpt-4o-mini",
        streaming=True
    )

    import random

    # Generate a random 3-digit number
    random_number = random.randint(100, 999)

    # Convert it to a string
    random_number_string = str(random_number)

    system_message = SystemMessage(content=f"""
    Debes mostrarle al usuario su carrito para finalizar la compra. 
    Muestra el precio, cantidad y link para cada producto, así como el precio total.
                                   
    Si el el carrito está vacio, indícale que no hay productos y que no se puede realizar la compra. No confundir carritos de compras anteriores con la compra actual.
                                   
    Si el carrito tiene productos, dile al usuario que para completar la compra debe escribir el siguiente codigo: {random_number_string}

    SIEMPRE USA EL CODIGO {random_number_string}, sin importar los codigos en mensajes anteriores.

    SIEMPRE DEBES MOSTRAR EL CARRITO QUE VA A COMPRAR EL USUARIO
                                   """)

    conversation = [system_message] + state["messages"][-20:]
    response = model.invoke(conversation)

    from backend.db import update_key 
    
    update_key(state["user_id"], random_number_string)

    return {
            "messages": [response]
    }

# Define the structure (nodes and directional edges between nodes) of the graph
#graph.add_edge(START, "")
graph.add_node("modelNode", _call_model)
graph.add_node("handle_shopping_tools", handle_shopping_tools)
graph.add_node("save_memory", save_memory)
graph.add_node("add_preferences", add_preferences)
graph.add_node("create_key", create_key)
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