from openai import OpenAI

class JaiQu:
    openai_client = None

    @classmethod
    def init(cls, openai_api_key: str):
        if cls.openai_client is None:
            cls.openai_client = OpenAI(api_key=openai_api_key)
