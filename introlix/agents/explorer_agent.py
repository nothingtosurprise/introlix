"""
The Explorer Agent retrieves and analyzes information from the internet using
SearXNG search and web crawling. It operates on multiple topics in parallel,
stores content in a vector database, and generates structured summaries for
efficient downstream processing.

Input Format:
==============================================================================
QUERIES: <list of search queries or research topics>
UNIQUE_ID: <workspace identifier for data isolation>
GET_ANSWER: <true | false - whether to generate summary answers>
MAX_RESULTS: <maximum number of search results per query>
MODEL: <LLM model identifier for content analysis>
==============================================================================

Output Format:
==============================================================================
EXPLORER_OUTPUT: [{
    "title": ["<webpage title 1>", "<webpage title 2>"],
    "description": ["<webpage description 1>", "<webpage description 2>"],
    "url": "<url>",
    "chunk_text": "<detailed summary of content relevant to the topic>",
    "score": <0.0-1.0 score indicating content relevance>,
}[]
==============================================================================

Workflow:
---------
1. Search for relevant URLs using SearXNG
2. Crawl and extract content from web pages in parallel
3. Chunk content with semantic similarity filtering (threshold: 0.35)
4. Store chunks in Chromadb vector database with workspace isolation
5. Retrieve relevant chunks
6. Retry failed queries up to max_retries times

Notes:
------
- Uses Chromadb for vector storage with workspace (unique_id) isolation
- Processes queries in batches of 5 to avoid search tool timeouts
- Implements semantic similarity filtering to store only relevant chunks
- Automatically retries queries that don't find sufficient data
- Embedding model: all-MiniLM-L6-v2
"""

import asyncio

import hashlib
from typing import List, Union
from pydantic import BaseModel, Field
import chromadb
from introlix.config import MIN_RELEVANCE_SCORE, CHROMA_DB_DIR, CHUNK_SIZE, CHUNK_OVERLAP_SIZE
from introlix.tools.web_crawler import web_crawler, ScrapeResult
from introlix.tools.web_search import SearXNGClient, duckduckgo_search
from introlix.utils.text_chunker import TextChunker
from introlix.state import app_state
from sentence_transformers import SentenceTransformer


class ExplorerAgentOutput(BaseModel):
    title: str = Field(description="The list title of the web page")
    description: str = Field(description="The list description of the web page")
    url: str = Field(description="The list url of the web page")
    chunk_text: str = Field(description="Chunk of the web page according to the topic")
    score: float = Field(description="The score of the sources between 0.0 and 1.0")


class ExplorerAgent:
    def __init__(self):
        self.chroma_client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
        self.embedding_model = app_state.embedding_model or SentenceTransformer(
            "all-MiniLM-L6-v2"
        )
        self.MAX_CONCURRENT_URLS = 30

    def _get_collection(self, unique_id: str):
        """
        Dynamically gets or creates an isolated workspace collection on the disk.
        """
        clean_id = f"workspace_{unique_id.replace('-', '_')}"
        return self.chroma_client.get_or_create_collection(name=clean_id)

    async def run(
        self,
        queries: list,
        unique_id: str,
        get_answer: bool,
        max_results=5,
        model="gemini-2.5-flash",
        retry: int = 0,
        max_retries: int = 5,
        queries_to_process: list = None,
    ) -> Union[ExplorerAgentOutput, List[ExplorerAgentOutput], None]:
        self.queries = queries
        self.unique_id = unique_id
        self.get_answer = get_answer
        self.max_results = max_results
        self.model = model
        self.search_tool = SearXNGClient(model=model)

        if retry > max_retries:
            return []

        queries_to_search = queries_to_process if queries_to_process else self.queries

        if self.get_answer:
            all_answers = []
            queries_needing_data = [] # list of queries that need data retrieval

            tasks = [self.process_single_query(q) for q in queries_to_search]
            task_results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in task_results:
                if isinstance(result, Exception):
                    print(f"Error processing query: {result}")
                    continue
                found_results, new_queries_needing_data, _ = result
                queries_needing_data.extend(new_queries_needing_data)

                if found_results:
                    all_answers.extend(found_results)

            if queries_needing_data:
                await self.get_and_save_data(queries_needing_data)

                retry_results = await self.run(
                    queries=queries,
                    unique_id=unique_id,
                    get_answer=get_answer,
                    max_results=max_results,
                    model=model,
                    retry=retry + 1,
                    max_retries=max_retries,
                    queries_to_process=queries_needing_data,
                )

                if isinstance(retry_results, list):
                    for retry_result in retry_results:
                        if isinstance(retry_result, list):
                            for r in retry_result:
                                if getattr(r, "chunk_text", None):
                                    all_answers.append(r)
                        elif getattr(retry_result, "chunk_text", None):
                            all_answers.append(retry_result)
                elif (
                    retry_results
                    and getattr(retry_results, "chunk_text", None)
                    and len(retry_results.chunk_text) > 0
                ):
                    all_answers.append(retry_results)

            return all_answers
        else:
            await self.get_and_save_data(queries_to_search)
            return None

    async def process_single_query(self, query: str) -> tuple:
        results = []
        queries_needing_data = []
        all_answers = []

        try:
            collection = self._get_collection(self.unique_id)

            query_embedding = self.embedding_model.encode_query(query)
            query_results = collection.query(
                query_embeddings=[query_embedding],
                n_results=self.max_results,
                include=["documents", "metadatas", "distances"],
            )

            ids = query_results.get("ids", [[]])[0]
            documents = query_results.get("documents", [[]])[0]
            metadatas = query_results.get("metadatas", [[]])[0]
            distances = query_results.get("distances", [[]])[0]

            for idx in range(len(ids)):
                raw_distance = distances[idx] if distances else 1.0
                score = max(0.0, 1 - raw_distance / 2)
                if score <= MIN_RELEVANCE_SCORE:
                    continue
                meta = metadatas[idx]
                try:
                    data = {
                        "_id": ids[idx],
                        "title": meta.get("title", ""),
                        "description": meta.get("description", ""),
                        "url": meta.get("url", ""),
                        "chunk_text": documents[idx] or "",
                        "score": float(score),
                    }
                    if not data["chunk_text"]:
                        continue

                    data_obj = ExplorerAgentOutput(**data)
                    results.append(data_obj)
                except Exception as e:
                    print(f"Error parsing search hit: {e}")
                    continue
        except Exception as e:
            print(f"Error searching Chromadb for query '{query}': {e}")
            queries_needing_data.append(query)
            return results, queries_needing_data, all_answers

        if not results:
            queries_needing_data.append(query)
            return None, queries_needing_data, all_answers

        if self.get_answer:
            all_answers.append(results)

        return results, queries_needing_data, all_answers

    async def get_and_save_data(self, queries: list = None):
        QUERY_BATCH_SIZE = 10
        queries_to_process = queries if queries else self.queries
        collection = self._get_collection(self.unique_id)

        def save_records(records: list):
            if not records:
                return

            ids, metadatas, documents = [], [], []

            for record in records:
                ids.append(record["_id"])
                documents.append(record["chunk_text"])
                metadatas.append(
                    {
                        "unique_id": record["unique_id"],
                        "title": record["title"],
                        "description": record["description"],
                        "url": record["url"],
                        "chunk_id": record["chunk_id"],
                    }
                )

            embeddings = self.embedding_model.encode_document(documents, batch_size=32)
            collection.upsert(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents,
            )

        async def process_query(query: str):
            if not self.search_tool.host:
                search_results = await asyncio.to_thread(
                    duckduckgo_search, query, self.max_results
                )
            else:
                task_duckduckgo = asyncio.create_task(
                    asyncio.to_thread(duckduckgo_search, query, self.max_results)
                )
                task_search_tool = asyncio.create_task(
                    self.search_tool.search(query=query, max_results=self.max_results)
                )

                # Get the first completed search results (either from duckduckgo or the search tool)
                done, pending = await asyncio.wait(
                    {task_duckduckgo, task_search_tool}, return_when=asyncio.FIRST_COMPLETED
                )

                try:
                    search_results = done.pop().result()

                    # Cancel the slower search task to save resources
                    for task in pending:
                        task.cancel()
                except Exception as e:
                    if pending:
                        fallback_task = pending.pop()
                        try:
                            search_results = await fallback_task
                        except Exception as fallback_error:
                            search_results = []
                    else:
                        search_results = []

            crawl_tasks = []

            existing = await asyncio.to_thread(
                self.is_url_exists, [r.url for r in search_results]
            )
            urls_to_crawl = [r.url for r in search_results if r.url not in existing]

            url_semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_URLS)

            async def crawl_with_limit(url):
                async with url_semaphore:
                    return await self._crawl_and_chunk(query, url)

            for url in urls_to_crawl:
                if isinstance(url, Exception):
                    print(f"Error checking URL existence: {url}")
                    continue
                if url:
                    crawl_tasks.append(crawl_with_limit(url))

            if not crawl_tasks:
                return []

            flat_records = []
            for task in asyncio.as_completed(crawl_tasks):
                try:
                    rec_list = await task
                except Exception as e:
                    continue

                if isinstance(rec_list, list) and rec_list:
                    flat_records.extend(rec_list)
                    save_records(rec_list)
                elif isinstance(rec_list, Exception):
                    print(f"Error during crawling: {rec_list}")

            return flat_records

        total_queries = len(queries_to_process)
        for batch_start in range(0, total_queries, QUERY_BATCH_SIZE):
            batch_end = min(batch_start + QUERY_BATCH_SIZE, total_queries)
            batch_queries = queries_to_process[batch_start:batch_end]

            batch_results = await asyncio.gather(
                *[process_query(q) for q in batch_queries], return_exceptions=True
            )

            for q_res in batch_results:
                if isinstance(q_res, Exception):
                    print(f"Error during query processing: {q_res}")

    async def _crawl_and_chunk(self, query: str, url: str) -> list:
        try:
            crawled_result = await web_crawler(url=url)

            print(
                f"Crawled {url} for query '{query}' and got result length {len(crawled_result.text)}"
            )

            if isinstance(crawled_result, str):
                return []

            chunker = TextChunker(chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP_SIZE)
            chunks = chunker.chunk_text(
                crawled_result.text
                if isinstance(crawled_result, ScrapeResult)
                else crawled_result
            )

            chunk_texts = [chunk["text"] for chunk in chunks]

            # There is many empty chunks
            if not chunk_texts:
                return []

            query_embedding = self.embedding_model.encode_query(query)
            chunk_embeddings = self.embedding_model.encode_document(
                chunk_texts, batch_size=32
            )

            similarities = self.embedding_model.similarity(
                query_embedding, chunk_embeddings
            )[0]

            relevant_chunks = []
            similarity_threshold = 0.20

            for idx, chunk in enumerate(chunks):
                similarity_score = float(similarities[idx])

                if similarity_score >= similarity_threshold:
                    chunk_record = {
                        "_id": f"{hashlib.md5(url.encode()).hexdigest()}_chunk_{chunk['chunk_id']}",
                        "unique_id": self.unique_id,
                        "title": crawled_result.title,
                        "description": crawled_result.description,
                        "url": crawled_result.url,
                        "chunk_id": chunk["chunk_id"],
                        "chunk_text": chunk["text"],
                    }
                    relevant_chunks.append(chunk_record)

            return relevant_chunks
        except Exception as e:
            print(f"Error processing {url}: {e}")
            return []

    def is_url_exists(self, urls: list[str]) -> set[str]:
        collection = self._get_collection(self.unique_id)
        ids = [f"{hashlib.md5(u.encode()).hexdigest()}_chunk_0" for u in urls]

        existing = set()
        if not ids:
            return existing

        try:
            result = collection.get(ids=ids, include=["metadatas"])
            found_ids = set(result.get("ids", []))

            for url, _id in zip(urls, ids):
                if _id in found_ids:
                    existing.add(url)
        except Exception as e:
            print(f"Error testing ID existence: {e}")

        return existing

    def delete_workspace_data(self):
        """Drops the isolated workspace collection instantly from the disk storage footprint"""
        clean_id = f"workspace_{self.unique_id.replace('-', '_')}"
        try:
            self.chroma_client.delete_collection(name=clean_id)
        except Exception as e:
            print(f"Collection workspace already deleted or missing: {e}")


if __name__ == "__main__":
    explorer_agent = ExplorerAgent()
    results = asyncio.run(
        explorer_agent.run(
            queries=["best open source models in 2026"],
            unique_id="test8",
            get_answer=True,
            max_results=5,
        )
    )
    print(results)
