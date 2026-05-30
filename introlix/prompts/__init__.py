import os

context_agent_file = os.path.join(os.path.dirname(__file__), "context_agent.md")
chat_agent_file = os.path.join(os.path.dirname(__file__), "chat_agent.md")
edit_agent_file = os.path.join(os.path.dirname(__file__), "edit_agent.md")

with open(context_agent_file, "r") as f:
    context_agent_prompt = f.read()

with open(chat_agent_file, "r") as f:
    chat_agent_prompt = f.read()

with open(edit_agent_file, "r") as f:
    edit_agent_prompt = f.read()