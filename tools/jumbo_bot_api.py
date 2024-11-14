import os
import requests
from langchain_core.tools import tool

def start_uvicorn_server(ssh_key, aws_ip):
    """Starts the Uvicorn server on the AWS instance via SSH."""
    print("Starting Uvicorn server...")
    os.system(f"ssh -i {ssh_key} ubuntu@{aws_ip} 'bash ~/start_uvicorn.sh'")
    print("Uvicorn server started.")

def call_api(payload, api_url):
    """Sends a POST request to the specified API URL with a JSON payload."""
    try:
        print("Sending API request...")
        response = requests.post(api_url, json=payload)
        response.raise_for_status()  # Raise an error for HTTP error codes
        print("Response:", response.json())
        return f"Response: {response.json()}"
    except requests.exceptions.RequestException as e:
        print("Error:", e)
        return "Error"

import time
import os

from dotenv import load_dotenv
load_dotenv()

@tool
def make_list(urls):
    """
    Input a list with the URLs of the products you want to buy, and the tool buys those products.
    """
    password = os.getenv("PASSWORD")
    email = os.getenv("EMAIL")
    address = os.getenv("ADDRESS")

    payload = {
        "email": email,  
        "password": password,        
        "address": address,
        "urls": urls
    }
    
# AWS server info
    AWS_IP = os.getenv("AWS_IP")
    SSH_KEY = os.getenv("SSH_KEY")
    API_URL = f"http://{AWS_IP}:8000/run_bot"
    start_uvicorn_server(SSH_KEY, AWS_IP) 

    time.sleep(5)

    response = call_api(payload, API_URL)
    return response

