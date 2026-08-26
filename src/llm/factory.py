from langchain.chat_models import init_chat_model

from src.config import settings


def get_chat_model():
    return init_chat_model(settings.model_name)
