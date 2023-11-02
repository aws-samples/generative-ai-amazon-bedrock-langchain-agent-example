from langchain.agents.tools import Tool
from langchain.agents import load_tools
#from kendra_index_retriever import KendraIndexRetriever
from langchain.retrievers import AmazonKendraRetriever
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.llms.bedrock import Bedrock
#from langchain.chat_models import BedrockChat
import boto3
import requests
import os
import warnings
#warnings.filterwarnings('ignore')

# Instantiate boto3 clients and resources
boto3_session = boto3.Session(region_name=os.environ['AWS_REGION'])
bedrock_client = boto3_session.client(service_name="bedrock-runtime")

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
        kendra_index_id = os.environ['KENDRA_INDEX_ID']

        llm = Bedrock(client=bedrock_client, model_id="anthropic.claude-v2", region_name=os.environ['AWS_REGION']) # "anthropic.claude-instant-v1"
        # llm = BedrockChat(client=bedrock_client, model_id="anthropic.claude-v2", region_name=os.environ['AWS_REGION'])
        llm.model_kwargs = {'max_tokens_to_sample': 350} 

        retriever = AmazonKendraRetriever(index_id=kendra_index_id)
        '''retriever = KendraIndexRetriever(
            kendraindex=kendra_index_id, 
            awsregion=region, 
            return_source_documents=True
        )'''

        prompt_template = """
        \n\nHuman: The following is a friendly conversation between a human and an AI. 
        The AI is talkative and provides lots of specific details from its context.
        If the AI does not know the answer to a question, it truthfully says it 
        does not know.
        {context}
        Instruction: Based on the above documents, provide a detailed answer and source document for, {question} Answer "don't know" if not present in the document.
        \n\nAssistant:
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

        if 'source_documents' in result:
            print('Sources:')
            for d in result['source_documents']:
              print(d.metadata['source'])

        return result


tools = Tools().tools