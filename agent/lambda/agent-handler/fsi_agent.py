from langchain.agents.tools import Tool
from langchain.agents.conversational.base import ConversationalAgent
from langchain.agents import AgentExecutor
from tools import Tools
from datetime import datetime

class FSIAgent:
    
    def __init__(self, llm, memory) -> None:
        self.ai_prefix = "Assistant"
        self.human_prefix = "Human"
        self.llm = llm
        self.memory = memory
        self.tools_instance = Tools()  # Define tools_instance here
        self.agent = self.create_agent()

    def create_agent(self):
        # Initialize the agent with only the AnyCompany tool
        anycompany_tool = Tool(name="AnyCompany", func=self.tools_instance.kendra_search, description="Use this tool to answer questions about AnyCompany.")
        
        fsi_agent = ConversationalAgent.from_llm_and_tools(
            llm=self.llm,
            tools=[anycompany_tool],
            ai_prefix=self.ai_prefix,
            human_prefix=self.human_prefix,
            verbose=True,
            return_intermediate_steps=True,
            return_source_documents=True
        )

        agent_executor = AgentExecutor.from_agent_and_tools(
            agent=fsi_agent,
            tools=[anycompany_tool],
            verbose=True,
            memory=self.memory,
            return_source_documents=True,
            return_intermediate_steps=True
        )
        
        return agent_executor

    def run(self, input):
        print("Running FSI Agent with input: " + str(input))
        try:
            response = self.tools_instance.kendra_search(input)
        except ValueError as e:
            print(f"Error running agent: {e}")
            response = "Sorry! It appears we have encountered an issue."

        return response
