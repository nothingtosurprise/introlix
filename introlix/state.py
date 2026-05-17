from sentence_transformers import SentenceTransformer
from pinecone import Pinecone

class AppState:
    embedding_model: SentenceTransformer = None
    pc: Pinecone = None

app_state = AppState()