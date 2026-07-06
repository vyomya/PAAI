# Alibaba Cloud Deployment Proof

This project uses Alibaba Cloud Model Studio (DashScope) to serve 
the Qwen language model.

## API Integration (`llm.py`)

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    api_key=api_key,
    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    model="qwen-plus",
    temperature=0,
    max_retries=2,
)
```

The `base_url` points directly to Alibaba Cloud's DashScope 
international endpoint. All LLM inference — planning, classification, 
agent execution, preference extraction, and evaluation — runs through 
this endpoint.
