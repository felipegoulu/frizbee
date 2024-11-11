import os 
import time
import requests
from langchain_core.tools import tool
# Start Uvicorn on the server
def start_uvicorn_server(SSH_KEY, AWS_IP):
    print("Starting Uvicorn server...")
    os.system(f"ssh -i {SSH_KEY} ubuntu@{AWS_IP} 'bash ~/start_uvicorn.sh'")
    print("Uvicorn server started.")

def call_api(payload, API_URL):
    try:
        print("Sending API request...")
        response = requests.post(API_URL, json=payload)
        print("Response:", response.json())
        return f'''Response: {response.json()}'''
    except requests.exceptions.RequestException as e:
        print("Error:", e)
        return '''Error'''

@tool
def make_list(urls):
    '''
    Input a list with the urls of the products you want to buy, and the tool buys those products 
    '''
    payload = {
        "email": "fegoulu@itba.edu.ar",
        "password": "Londres1908",
        "address": "Avenida los bosques 1730",
        "urls": urls
        }

    # AWS server info
    AWS_IP = "3.136.87.137"
    SSH_KEY = "/Users/felipegoulu/projects/frizbee_aws_keypair.pem"
    API_URL = f"http://{AWS_IP}:8000/run_bot"
    start_uvicorn_server(SSH_KEY, AWS_IP) 

    time.sleep(5)

    response = call_api(payload, API_URL)
    return response