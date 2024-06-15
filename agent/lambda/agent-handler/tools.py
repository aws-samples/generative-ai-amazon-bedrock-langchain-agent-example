import os
import json
import boto3
from langchain.agents.tools import Tool
from urllib.parse import urlparse

bedrock = boto3.client('bedrock-runtime', region_name=os.environ['AWS_REGION'])


class Tools:

    def __init__(self) -> None:
        print("Initializing Tools")
        self.tools = [
            Tool(
                name="AnyCompany",
                func=self.kendra_search,
                description="Use this tool to answer questions about AnyCompany.",
            )
        ]

    def parse_kendra_response(self, kendra_response):
        """
        Extracts the source URI from document attributes in Kendra response.
        """
        modified_response = kendra_response.copy()

        result_items = modified_response.get('ResultItems', [])

        for item in result_items:
            source_uri = None
            if item.get('DocumentAttributes'):
                for attribute in item['DocumentAttributes']:
                    if attribute.get('Key') == '_source_uri':
                        source_uri = attribute.get('Value', {}).get('StringValue', '')

            if source_uri:
                print(f"Amazon Kendra Source URI: {source_uri}")
                item['_source_uri'] = source_uri

        return modified_response

    def kendra_search(self, question):
        """
        Performs a Kendra search using the Query API.
        """
        kendra = boto3.client('kendra')

        kendra_response = kendra.query(
            IndexId=os.getenv('KENDRA_INDEX_ID'),
            QueryText=question,
            PageNumber=1,
            PageSize=5  # Limit to 5 results
        )

        parsed_results = self.parse_kendra_response(kendra_response)

        print(f"Amazon Kendra Query Item: {parsed_results}")

        # passing in the original question, and various Kendra responses as context into the LLM
        return self.invokeLLM(question, parsed_results)

    def invokeLLM(self, question, context):
        """
        Generates an answer for the user based on the Kendra response.
        """
        prompt_data = f"""
        <Task>
        Act as an internal chatbot assistant for a company.
        </Task>
        <Instructions>
        You will be acting as an internal chatbot assistant for a company. Your role is to provide accurate and relevant information in response to specific questions from employees by checking your knowledge base from uploaded documents and using your general knowledge as a pre-trained Large Language Model. 

        Here are some important guidelines for the interaction:
        - Whenever a user asks a question, first refer to the provided context from the uploaded documents.
        - If the answer can be found in the uploaded documents, provide the information directly from there.
        - If the information is not available in the context, use your general knowledge to answer the question.
        - Always ensure the information is up-to-date and accurate. Cite the sources whenever applicable.
        - Respond quickly and in a friendly manner.
        - Format your response for enhanced human readability.

        Here is the user's question and the provided context:

        <question>{question}</question>
        <context>{context}</context>

        Based on the above guidelines, provide the best possible answer.
        </Instructions>
        """

        # Formatting the prompt as a JSON string
        json_prompt = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 3500,
            "temperature": 0.4,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt_data
                        }
                    ]
                }
            ]
        })

        # Invoking Claude3, passing in our prompt
        response = bedrock.invoke_model(
            body=json_prompt,
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            accept="application/json",
            contentType="application/json"
        )

        # Getting the response from Claude3 and parsing it to return to the end user
        response_body = json.loads(response['body'].read())
        answer = response_body['content'][0]['text']

        return answer


# Pass the initialized retriever and llm to the Tools class constructor
tools = Tools().tools
