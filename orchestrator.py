from langchain.chains import LLMChain
from langchain_community.chat_models import ChatOllama
from prompts import orchestrator_prompt
from agentic_framework import priority_agent, summarizer_agent, email_agent
from langchain.memory import ConversationBufferMemory


# Build router

llm = ChatOllama(model="mistral", temperature=0)

shared_memory = ConversationBufferMemory(
    memory_key="history",
    return_messages=True
)
# Combine everything into a MultiPromptChain
orchestrator = LLMChain(
    llm=llm,
    prompt=orchestrator_prompt,
    memory=shared_memory,
    verbose=True
)
import json

def orchestrate(user_input):
    router_output = orchestrator.run(user_input)
    print(f"Router raw output:\n{router_output}\n")

    # Try to parse JSON
    try:
        route = json.loads(router_output)
        destination = route.get("destination", "").lower()
    except json.JSONDecodeError:
        print("Router output not valid JSON. Defaulting to summarizer.")
        destination = "summarizer"

    # Dispatch
    if destination == "priority":
        result = priority_agent.run(user_input)
    elif destination == "emaildraft":
        result = email_agent.run(user_input)
    elif destination == "summarizer":
        result = summarizer_agent.run(user_input)
    else:
        print(f"Unknown destination '{destination}'. Defaulting to summarizer.")
        result = summarizer_agent.run(user_input)

    return result


if __name__ == "__main__":
    # Example usage
    user_input = "Summarize my recent emails and create a todo list."
    response = orchestrate(user_input)
    print(response)
