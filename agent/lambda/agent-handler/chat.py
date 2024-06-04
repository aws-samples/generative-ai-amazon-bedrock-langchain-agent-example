from boto3.dynamodb.types import TypeSerializer
from langchain.memory.chat_message_histories import DynamoDBChatMessageHistory
from langchain.memory import ConversationBufferMemory
from datetime import datetime
import json
import boto3
import os

now = datetime.utcnow()
dynamodb = boto3.client('dynamodb')
ts = TypeSerializer()

# Create reference to DynamoDB tables
conversation_index_table_name = os.environ.get('CONVERSATION_INDEX_TABLE')
conversation_table_name = os.environ.get('CONVERSATION_TABLE')

class Chat():

    def __init__(self, event, session_id):
        print(f"Initializing FSI Agent chat with session ID: {session_id}")
        self.set_user_id(event)
        self.set_session_id(session_id)
        self.set_chat_index()
        self.set_memory(event, session_id)
        self.create_new_chat()

    def set_memory(self, event, session_id):
        # Set up session id
        if session_id != self.session_id:
            self.set_session_id(session_id)
        conversation_id = self.session_id
        
        # Set up conversation history
        self.message_history = DynamoDBChatMessageHistory(table_name=conversation_table_name, session_id=conversation_id)
        if 'Human' in event:
            self.message_history.add_user_message(event['Human'])
        elif 'Assistant' in event:
            self.message_history.add_ai_message(event['Assistant'])

        # Set up conversation memory
        self.memory = ConversationBufferMemory(
            ai_prefix="Assistant",
            memory_key="chat_history",
            chat_memory=self.message_history,
            input_key="input",
            output_key="output",
            return_messages=True
        )

    def get_chat_index(self):
        key = {'id':self.user_id}
        chat_index = dynamodb.get_item(TableName=conversation_index_table_name, Key=ts.serialize(key)['M'])
        if 'Item' in chat_index:
            return int(chat_index['Item']['chat_index']['N'])
        return 0

    def increment_chat_index(self):
        self.chat_index += 1
        input = {
            'id': self.user_id,
            'chat_index': self.chat_index,
            'updated_at': str(now)
        }
        dynamodb.put_item(TableName=conversation_index_table_name, Item=ts.serialize(input)['M'])

    def create_new_chat(self):
        self.increment_chat_index()

    def set_user_id(self, event):
        self.user_id = "Demo User"

    def set_session_id(self, session_id):
        self.session_id = session_id

    def set_chat_index(self):
        self.chat_index = self.get_chat_index()