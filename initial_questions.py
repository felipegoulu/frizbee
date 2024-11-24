# initial_questions.py
import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage
def toggle_restriction(choice):
    if choice in st.session_state.selected_restrictions:
        st.session_state.selected_restrictions.remove(choice)
    else:
        st.session_state.selected_restrictions.add(choice)

def toggle_category(choice):
    if choice in st.session_state.selected_categories:
        st.session_state.selected_categories.remove(choice)
    else:
        st.session_state.selected_categories.add(choice)

# Agregar estas funciones junto a los otros toggles
def toggle_budget(choice):
    if choice in st.session_state.selected_budget:
        st.session_state.selected_budget.remove(choice)
    else:
        st.session_state.selected_budget = {choice}  # Solo se puede elegir uno

def toggle_people(choice):
    if choice in st.session_state.selected_people:
        st.session_state.selected_people.remove(choice)
    else:
        st.session_state.selected_people = {choice}  # Solo se puede elegir uno

def finish_restrictions():
    selecciones = list(st.session_state.selected_restrictions)
    st.session_state.user_choices["restricciones_alimentarias"] = (selecciones)
    st.session_state.restrictions_answered = True

def finish_categories():
    selecciones = list(st.session_state.selected_categories)
    st.session_state.user_choices["categorias_a_comprar"] = selecciones
    st.session_state.categories_answered = True

# Agregar estas funciones junto a los otros finish
def finish_budget():
    selecciones = list(st.session_state.selected_budget)
    st.session_state.user_choices["presupuesto"] = selecciones
    st.session_state.budget_answered = True

def finish_people():
    selecciones = list(st.session_state.selected_people)
    st.session_state.user_choices["numero_de_personas"] = selecciones
    st.session_state.people_answered = True
    st.session_state.messages.append(HumanMessage(content="Empieza")) 


def show_initial_questions(BOT_AVATAR):
    # Inicializar estados
    if 'user_choices' not in st.session_state:
        st.session_state.user_choices = [] 
        st.session_state.user_choices = {"restricciones_alimentarias": [], "categorias_a_comprar": [], "presupuesto": [], "numero_de_personas": []}

    if 'selected_restrictions' not in st.session_state:
        st.session_state.selected_restrictions = set()
    if 'selected_categories' not in st.session_state:
        st.session_state.selected_categories = set()
    if 'restrictions_answered' not in st.session_state:
        st.session_state.restrictions_answered = False
    if 'categories_answered' not in st.session_state:
        st.session_state.categories_answered = False
    if 'selected_budget' not in st.session_state:
        st.session_state.selected_budget = set()
    if 'selected_people' not in st.session_state:
        st.session_state.selected_people = set()
    if 'budget_answered' not in st.session_state:
        st.session_state.budget_answered = False
    if 'people_answered' not in st.session_state:
        st.session_state.people_answered = False

    # Primera pregunta - Restricciones alimentarias
    if not st.session_state.restrictions_answered:
        chat_container = st.chat_message("assistant", avatar=BOT_AVATAR)
        with chat_container:
            st.write("¡Hola! Soy tu asistente de compras. ¿Tienes alguna restricción alimentaria?")
            st.write("Puedes seleccionar múltiples opciones")
            
            col1, col2 = st.columns(2)
            with col1:
                st.checkbox("Soy vegetariano", key="vegetariano", 
                        on_change=toggle_restriction, args=("vegetariano",))
                st.checkbox("Intolerante a la lactosa", key="lactosa", 
                        on_change=toggle_restriction, args=("lactosa",))
                st.checkbox("No tengo restricciones", key="ninguna", 
                        on_change=toggle_restriction, args=("ninguna",))
            with col2:
                st.checkbox("Soy vegano", key="vegano", 
                        on_change=toggle_restriction, args=("vegano",))
                st.checkbox("Paleo", key="paleo", 
                        on_change=toggle_restriction, args=("paleo",))
                st.checkbox("No tomo alcohol", key="no_alcohol", 
                        on_change=toggle_restriction, args=("no_alcohol",))
            
            if st.button("Continuar con estas selecciones"):
                finish_restrictions()
                chat_container.empty()
                st.rerun()

    # Segunda pregunta - Categorías a comprar
    elif not st.session_state.categories_answered:
        chat_container = st.chat_message("assistant", avatar=BOT_AVATAR)
        with chat_container:
            st.write("¿Qué categorías te gustaría comprar hoy?")
            st.write("Puedes seleccionar múltiples opciones")
            
            col1, col2 = st.columns(2)
            with col1:
                st.checkbox("Vegetales", key="veg", 
                        on_change=toggle_category, args=("vegetales",))
                st.checkbox("Frutas", key="fruit", 
                        on_change=toggle_category, args=("frutas",))
                st.checkbox("Carnes", key="meat", 
                        on_change=toggle_category, args=("carnes",))
                st.checkbox("Lácteos", key="dairy", 
                        on_change=toggle_category, args=("lacteos",))
            with col2:
                st.checkbox("Bebidas", key="drinks", 
                        on_change=toggle_category, args=("bebidas",))
                st.checkbox("Snacks", key="snacks", 
                        on_change=toggle_category, args=("snacks",))
                st.checkbox("Limpieza", key="cleaning", 
                        on_change=toggle_category, args=("limpieza",))
                st.checkbox("dulces", key="dulces", 
                        on_change=toggle_category, args=("dulces",))
            
            if st.button("Comenzar mi compra"):
                finish_categories()
                chat_container.empty()
                st.rerun()

    elif not st.session_state.budget_answered:
        chat_container = st.chat_message("assistant", avatar=BOT_AVATAR)
        with chat_container:
            st.write("¿Tienes un presupuesto específico en mente?")
            
            col1, col2 = st.columns(2)
            with col1:
                st.checkbox("Económico", key="economico", 
                        on_change=toggle_budget, args=("económico",))
                st.checkbox("Premium", key="premium", 
                        on_change=toggle_budget, args=("premium",))
            with col2:
                st.checkbox("Moderado", key="moderado", 
                        on_change=toggle_budget, args=("moderado",))
                st.checkbox("Sin límite específico", key="sin_limite", 
                        on_change=toggle_budget, args=("sin límite específico",))
            
            if st.button("Continuar"):
                finish_budget()
                chat_container.empty()
                st.rerun()

    elif not st.session_state.people_answered:
        chat_container = st.chat_message("assistant", avatar=BOT_AVATAR)
        with chat_container:
            st.write("¿Para cuántas personas estás comprando?")
            
            col1, col2 = st.columns(2)
            with col1:
                st.checkbox("Solo para mí", key="solo", 
                        on_change=toggle_people, args=("una persona",))
                st.checkbox("Para 4-5 personas", key="4-5", 
                        on_change=toggle_people, args=("4-5 personas",))
            with col2:
                st.checkbox("Para 2-3 personas", key="2-3", 
                        on_change=toggle_people, args=("2-3 personas",))
                st.checkbox("Para más de 5 personas", key="5+", 
                        on_change=toggle_people, args=("más de 5 personas",))
            
            if st.button("Finalizar"):
                finish_people()
                chat_container.empty()
                st.rerun()
                
    return st.session_state.user_choices