from langchain_openai import ChatOpenAI
from paai.tools import tools

from paai.config import settings


llm = ChatOpenAI(
    api_key=settings.dashscope_api_key,
    model="gpt-4o-mini",
    temperature=0,
    max_retries=0,
)

# Bind tools to model
llm_with_tools = llm.bind_tools(tools)
