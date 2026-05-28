from sentence_transformers import SentenceTransformer

class AppState:
    embedding_model: SentenceTransformer = None

app_state = AppState()