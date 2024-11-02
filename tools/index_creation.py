# first we connect to pinecone and create de pinecone index
import os
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()
# initialize connection to pinecone
api_key = os.environ.get('PINECONE_API_KEY') 
# configure client
pc = Pinecone(api_key=api_key)
# index specification
from pinecone import ServerlessSpec
cloud = os.environ.get('PINECONE_CLOUD') or 'aws'
region = os.environ.get('PINECONE_REGION') or 'us-east-1'
spec = ServerlessSpec(cloud=cloud, region=region)
# choose a name for your index
index_name = "walmart-search"

#for parse-dense index in Pinecone we must set metric="dotproduct" and 
# align the dimension value to that of our retrieval model, which outputs 512-dimensional vectors.

import time
# check if index already exists (it shouldn't if this is first time)
if index_name not in pc.list_indexes().names():
    # if does not exist, create index
    pc.create_index(
        index_name,
        dimension=512,
        metric='dotproduct',
        spec=spec
    )
    # wait for index to be initialized
    while not pc.describe_index(index_name).status['ready']:
        time.sleep(1)

# connect to index
index = pc.Index(index_name)
# view index stats
print(index.describe_index_stats())



