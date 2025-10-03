from langchain_openai import ChatOpenAI
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplat
from langchain.memory import ConversationBufferMemory
from langchain.agents import AgentExecutor, Tool
from prompts import priority_prompt, summarizer_prompt, emaildraft_prompt

# Each agent can share this memory (so updates persist)
shared_memory = ConversationBufferMemory(
    memory_key="history", 
    input_key="input", 
    return_messages=True
)
from langchain.chat_models import ChatOpenAI
from langchain.chains import LLMChain
from langchain.agents import initialize_agent

llm = ChatOpenAI(model="gpt-4", temperature=0)

# Priority Agent
priority_chain = LLMChain(llm=llm, prompt=priority_prompt, memory=shared_memory)
priority_agent = initialize_agent(
    tools, llm, agent="chat-conversational-react-description",
    memory=shared_memory, verbose=True
)

# Summarizer Agent
summarizer_chain = LLMChain(llm=llm, prompt=summarizer_prompt, memory=shared_memory)
summarizer_agent = initialize_agent(
    tools, llm, agent="chat-conversational-react-description",
    memory=shared_memory, verbose=True
)

# Email Draft Agent
email_chain = LLMChain(llm=llm, prompt=emaildraft_prompt, memory=shared_memory)
email_agent = initialize_agent(
    tools, llm, agent="chat-conversational-react-description",
    memory=shared_memory, verbose=True
)

