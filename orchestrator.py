from langchain.chains.router import MultiPromptChain, RouterChain
from langchain.chains.router.llm_router import LLMRouterChain, RouterOutputParser
from langchain_openai import ChatOpenAI
from prompts import orchestrator_prompt, priority_prompt, summarizer_prompt, emaildraft_prompt
from agentic_framework import priority_chain, summarizer_chain, email_chain

# Router prompts
destinations = {
    "priority": priority_prompt.template,
    "summarizer": summarizer_prompt.template,
    "email": emaildraft_prompt.template,
}

# Build router

llm = ChatOpenAI(model="gpt-4", temperature=0)

router_chain = LLMRouterChain.from_llm(llm, orchestrator_prompt)

# Combine everything into a MultiPromptChain
orchestrator = MultiPromptChain(
    router_chain=router_chain,
    destination_chains={
        "priority": priority_chain,
        "summarizer": summarizer_chain,
        "email": email_chain
    },
    default_chain=summarizer_chain,  # fallback
    verbose=True
)
