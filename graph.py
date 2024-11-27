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


graph = StateGraph(GraphsState)

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

# List of tools that will be accessible to the graph via the ToolNode
tools = [product_lookup_tool, add_product, remove_product, change_quantity]

tools_by_name = {tool.name: tool for tool in tools}

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

# Core invocation of the model
def _call_model(state: GraphsState):
    cart_info = f'''\nCarrito actual: {state["cart"]}'''
    system_prompt = SystemMessage(f'''
Eres un asistente de compras del supermercado Jumbo que ayuda a realizar la compra semanal. Debes ser conversacional y hacer preguntas personalizadas basadas en las respuestas del usuario.


INSTRUCCIONES:
1. Sigue el orden de las categorías seleccionadas
2. Para cada categoría:
   - Haz preguntas abiertas sobre preferencias y hábitos, siempre que hagas una pregunta trata de poner algunos productos que puedan responder a esa pregunta.
   - Adapta tus siguientes preguntas según las respuestas
   - Sugiere productos basados en lo que vas aprendiendo del usuario
   - Haz preguntas de seguimiento relevantes
   - Trata de hacer la menos cantidad de preguntas posibles, la idea es que el usuario no tenga que escribir mucho
   - En vez de preguntar que producto prefiere, pregunta si le parece que esta bien si agregas esos productos al carrito o quiere otros
3. Empieza tu con la categoria que tu quieras
4. Si el mensaje del usuario es Empieza, debes introducirte y luego empezar por la categoria primera. 
5. Antes de pasar a la siguiente categoria, pregunta si quiere algun otro producto, mencionando uno que a ti se te ocurra que pueda faltar


REGLAS IMPORTANTES:
1. Adapta las preguntas según:
   - Las respuestas previas del usuario
   - Sus restricciones alimentarias
   - El número de personas
   - El presupuesto indicado

2. Sé conversacional y natural:
   - Haz preguntas de seguimiento relevantes
   - Muestra interés en las preferencias del usuario
   - Ofrece sugerencias personalizadas
   - Aprende de las respuestas para hacer mejores recomendaciones

3. Mantén un enfoque útil:
   - Si el usuario muestra interés en algo específico, profundiza en eso
   - Si muestra desinterés, pasa a otra subcategoría
   - Adapta las cantidades según el tamaño del hogar
   - Considera el presupuesto en tus sugerencias

RECUERDA:
- No sigas un guion rígido
- Adapta tus preguntas según la conversación
- Aprende de las respuestas del usuario
- Sé flexible y natural en el diálogo
- Haz preguntas relevantes para entender mejor los gustos y necesidades


PROCESO:
1. Sigue el orden exacto de categorías
2. Para cada categoría:
   - Sugiere algunos productos como ejemplos
   - Deja que el usuario elija libremente qué quiere comprar
   - No limites al usuario a tus sugerencias
   - Solo avanza cuando el usuario termine con esa categoría
3. si usuario le pide un producto (por ejemplo, zanahoria), agrega zanahoria al carrito sin preguntar cual zanahoria quiere


IMPORTANTE:
- Tus sugerencias son solo ejemplos/inspiración
- El usuario puede elegir cualquier producto, no solo los sugeridos
- No preguntes "¿cuáles de estos quiere?"
- Pregunta abiertamente qué quiere comprar de cada categoría
- Mantén un tono amigable y eficiente
- No mostrar imagenes
- El carrito debe tener productos de la base de datos SIEMPRE. Nunca inventar productos!

Para buscar productos del supermercado, debes usar la tool product_lookup_tool. Trata de buscar productos en especificos, si quieres buscar vegetales, trata de buscar los prdouctos usando la tool multiples veces.
Para agregar productos , debes usar la tool add_products y poner como input el nombre, cantidad, precio, link y el carrito actual. IMPORTANTE: los productos que agregues al carrito deben ser productos que esten en la base de datos con la misma informacion.

Para usar la herramienta, necesitas enviar los productos que debes buscar en la base de datos. La herramienta recuperará esos productos. Busca un producto a la vez. Si la herramienta no recupera la información necesaria, intenta de nuevo hasta que obtengas el producto correcto; nunca inventes productos.

Carrito actual: {cart_info}

GUSTOS DEL USUARIO:
Me gusta la comida mediterránea, sobre todo las comidas italianas y españolas. Me gusta la pasta italiana, recetas como pasta alla bolognesa, pasta con zucchini y guanciales, pasta alla norma, risotto, etc. Como soy argentino, también me gusta comer mucha carne, me gustan todos los tipicos de carne. Me gustan todos los vegetales y las frutas. 
En cuanto a las bebidas, me gustan mucho el vino y la cerveza.
En cuanto a snacks salados, me gustan las papas.
En cuanto a snacks dulces  me gustan los chocolates amargos.
De desayuno suelo comer yogurt con frutas y granola o huevos revueltos.


          ''')

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
graph.add_edge(START, "modelNode")
graph.add_node("product_lookup", product_lookup_tool)
graph.add_node("modelNode", _call_model)
graph.add_node("add_product", add_product)
graph.add_node("remove_product", remove_product)
graph.add_node("change_quantity", change_quantity)

# Add conditional logic to determine the next step based on the state (to continue or to end)
graph.add_conditional_edges(
    "modelNode",
    determine_tool_node,  # This function will decide the flow of execution
)

graph.add_edge("product_lookup", "modelNode")
graph.add_edge("add_product", "modelNode")
graph.add_edge("remove_product", "modelNode")
graph.add_edge("change_quantity", "modelNode")

# Compile the state graph into a runnable object
graph_runnable = graph.compile()