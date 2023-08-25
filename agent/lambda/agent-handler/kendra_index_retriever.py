"""Chain for question-answering against a vector database."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain.schema import BaseRetriever, Document

from kendra_results import kendra_query, kendra_client
import boto3

class KendraIndexRetriever(BaseRetriever):
    """Retriever to retrieve documents from Amazon Kendra index.

    Example:
        .. code-block:: python

            kendraIndexRetriever = KendraIndexRetriever()

    """

    kendraindex: str
    """Kendra index id"""
    awsregion: str
    """AWS region of the Kendra index"""
    k: int
    """Number of documents to query for."""
    return_source_documents: bool
    """Whether source documents to be returned """
    kclient: Any
    """ boto3 client for Kendra. """
    
    def __init__(self, kendraindex, awsregion, k=3, return_source_documents=False):
        print("Initializing Kendra Index Retriever")
        self.kendraindex = kendraindex
        self.awsregion = awsregion
        self.k = k
        self.return_source_documents = return_source_documents
        self.kclient = kendra_client(self.kendraindex, self.awsregion)
        
    def get_relevant_documents(self, query: str) -> List[Document]:
        print("Providing Relevant Kendra Documents")
        """Run search on Kendra index and get top k documents

        docs = get_relevant_documents('This is my query')
        """
        docs = kendra_query(self.kclient, query, self.k, self.kendraindex)
        return docs
    
    async def aget_relevant_documents(self, query: str) -> List[Document]:
        return await super().aget_relevant_documents(query)
