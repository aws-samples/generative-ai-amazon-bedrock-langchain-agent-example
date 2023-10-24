from langchain.agents.tools import Tool
from langchain.agents.conversational.base import ConversationalAgent
from langchain.agents import AgentExecutor
from tools import tools
from datetime import datetime


PREFIX = "\n\nHuman: You are a Financial Services AI chatbot (Assistant) for a company called Octank Financial. You can also can answer general questions about anything. You quickly respond to questions from a user with an answer and the source documents you used to find your answer in the format: \
            [Source 1: Source Title 1 - Source Link 1], \
            [Source 2: Source Title 2 - Source Link 2], \
            [Source n: Source Title n - Source Link n]. Provide two newline characters between your answer and the source documents. By the way, the date is " + datetime.now().strftime("%m/%d/%Y, %H:%M:%S") + ".\n\nAssistant:"


FORMAT_INSTRUCTIONS = """To use a tool, please use the following format:
Thought: Do I need to use a tool? Yes
Action: The action to take from the following list of pre-defined tools: 'Octank Financial'
Action Input: The input to the action
Observation: The result of the action

Thought: Do I need to use a tool? No
Assistant: [answer and source documents]
"""

class FSIAgent():
    def __init__(self,llm, memory) -> None:
        self.prefix = PREFIX
        self.ai_prefix = "Assistant"
        self.human_prefix = "Human"
        self.llm = llm
        self.memory = memory
        self.format_instructions = FORMAT_INSTRUCTIONS
        self.agent = self.create_agent()


    def create_agent(self):
        fsi_agent = ConversationalAgent.from_llm_and_tools(
            llm = self.llm,
            tools = tools,
            prefix = self.prefix,
            ai_prefix = self.ai_prefix,
            human_prefix = self.human_prefix,
            format_instructions = self.format_instructions,
            return_intermediate_steps = True,
            return_source_documents = True
        )
        agent_executor = AgentExecutor.from_agent_and_tools(agent=fsi_agent, tools=tools, verbose=True, memory=self.memory, return_intermediate_steps=True, return_source_documents=True)
        return agent_executor


    def run(self, input):
        print("Running FSI Agent with input: " + str(input))
        return self.agent(input)
