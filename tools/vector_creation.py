# Im going to create the sparse vectors using BM25.
# Establish connection with db.

import psycopg2
import pandas as pd
import os
from dotenv import load_dotenv
load_dotenv()

# Connect to your PostgreSQL database
conn = psycopg2.connect(
    dbname=os.getenv("DB_NAME"), 
    user=os.getenv("DB_USER"), 
    password=os.getenv("DB_PASSWORD"), 
    host=os.getenv("DB_HOST"), 
    port=os.getenv("DB_PORT")
)

query = "SELECT product_name, department, category, subcategory, price_current, product_url FROM walmart_78130"

metadata = pd.read_sql(query, conn)

conn.close()

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

from langchain_openai import OpenAIEmbeddings

EMBEDDINGS_DIMENSIONS = 512

embedding_client = OpenAIEmbeddings(api_key=OPENAI_API_KEY,
    model="text-embedding-3-small", dimensions=EMBEDDINGS_DIMENSIONS)
     
from pinecone_text.sparse import BM25Encoder

bm25 = BM25Encoder()

# Fit BM25 on the extracted product names
bm25.fit(metadata['product_name'])

import pickle

# Save the fitted BM25 model to a file
with open('bm25_model.pkl', 'wb') as f:
    pickle.dump(bm25, f)

# Load the BM25 model from the file
with open('bm25_model.pkl', 'rb') as f:
    bm25 = pickle.load(f)

from pinecone import Pinecone

# initialize connection to pinecone
api_key = os.environ.get('PINECONE_API_KEY') 

# connect to index
pc = Pinecone(api_key=api_key)
index_name = 'walmart-search'
pinecone_index = pc.Index(index_name)

from tqdm.auto import tqdm

batch_size = 500

for i in tqdm(range(0, len(metadata), batch_size)):
    # find the end of batch
    i_end = min(i + batch_size, len(metadata))
    # extract metadata batch
    meta_batch = metadata.iloc[i:i_end]
    meta_dict = meta_batch.to_dict(orient="records")

    def clean_metadata(metadata):
        cleaned = {}
        for k, v in metadata.items():
            if v is not None:
                cleaned[k] = v
            else:
                cleaned[k] = ''
        return cleaned

    # Apply clean_metadata to each dictionary in the list
    meta_dict = [clean_metadata(row) for row in meta_dict]
    meta_batch_list = meta_batch[['product_name', 'department', 'category', 'subcategory']].values.tolist()  # Convert the DataFrame to a list of rows
    meta_batch = []

    # Iterate through each row in the list of rows
    for row in meta_batch_list:
        concatenated_row = ""
        # Iterate through each value in the row
        for value in row:
            if value is not None:
                concatenated_row += str(value) + " "  # Convert to string and add a space
            else:
                concatenated_row += " "  # Add a space if the value is None
        # Strip any trailing spaces and append the concatenated string to the result list
        meta_batch.append(concatenated_row.strip())

    # create sparse BM25 vectors
    sparse_embeds = bm25.encode_documents(meta_batch)
    # Create dense vectors using text-embedding-ada-002
    dense_embeds = embedding_client.embed_documents(meta_batch)
    # create unique IDs
    ids = [str(x) for x in range(i, i_end)]
    upserts = []
    # loop through the data and create dictionaries for uploading documents to pinecone index
    for _id, sparse, dense, meta in zip(ids, sparse_embeds, dense_embeds, meta_dict):
        upserts.append({
            'id': _id,
            'sparse_values': sparse,
            'values': dense,  # Dense vector (can be zeros if not used)
            'metadata': meta  # Metadata (optional)
        })
    # upload the documents to the new hybrid index
    pinecone_index.upsert(upserts)

# show index description after uploading the documents
print(pinecone_index.describe_index_stats())

