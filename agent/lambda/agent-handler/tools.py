from langchain.agents.tools import Tool
from langchain.agents import load_tools
from kendra_index_retriever import KendraIndexRetriever
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.llms.bedrock import Bedrock

import requests
import os

kendra_index_id = os.environ['KENDRA_INDEX_ID']

class Tools():

    def __init__(self) -> None:
        print("Initializing Tools")
        self.tools = [
            Tool(
                name="Octank Financial",
                func=self.chain_tool,
                description="Use this tool to answer questions about Octank Financial.",
            )
        ]


    def build_chain(self):
        print("Building Chain")
        region = os.environ['AWS_REGION']

        llm = Bedrock(
            model_id="anthropic.claude-instant-v1"
        )  
        llm.model_kwargs = {'max_tokens_to_sample': 200} 

        retriever = KendraIndexRetriever(
            kendraindex=kendra_index_id, 
            awsregion=region, 
            return_source_documents=True
        )

        prompt_template = """
        The following is a friendly conversation between a human and an AI. 
        The AI is talkative and provides lots of specific details from its context.
        If the AI does not know the answer to a question, it truthfully says it 
        does not know.
        {context}
        Instruction: Based on the above documents, provide a detailed answer and source document for, {question} Answer "don't know" if not present in the document. Solution:
        """

        PROMPT = PromptTemplate(
          template=prompt_template, input_variables=["context", "question"]
        )
        chain_type_kwargs = {"prompt": PROMPT}
        return RetrievalQA.from_chain_type(
          llm, 
          chain_type="stuff", 
          retriever=retriever, 
          chain_type_kwargs=chain_type_kwargs,
          return_source_documents=True
        )


    def run_chain(self, chain, prompt: str, history=[]):
        print("Running Chain")
        result = chain(prompt)

        return {
            "answer": result['result'],
            "source_documents": result['source_documents']
        }


    def chain_tool(self, input):
        chain = self.build_chain()
        result = self.run_chain(chain, input)
        print("Chain-of-Thought result = " + str(result))

        if 'source_documents' in result:
            print('Sources:')
            for d in result['source_documents']:
              print(d.metadata['source'])

        return result


tools = Tools().tools