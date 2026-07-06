from langchain_openai import ChatOpenAI
from tool import tools

# f = open('openAIkey.txt', 'r')
# api_key = f.read().strip()
# f.close() 


# llm = ChatOpenAI(
#     api_key=api_key,
#     model="gpt-4o-mini",
#     temperature=0,
#     max_retries=0,
# )

# # Bind tools to model
# llm_with_tools = llm.bind_tools(tools)

f = open('qwenkey.txt', 'r')
api_key = f.read().strip()
f.close()

llm = ChatOpenAI(
    api_key=api_key,
    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",  # international
    model="qwen-plus",
    temperature=0,
    max_retries=2,
)

llm_with_tools = llm.bind_tools(tools)