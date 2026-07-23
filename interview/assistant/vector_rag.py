"""
向量 RAG 模块

基于 BAAI/bge-m3 嵌入模型 + Milvus 向量数据库的语义检索。
"""
from typing import Optional

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_milvus import Milvus
from pymilvus import connections, utility

from .config import config

COLLECTION_NAME = "resume_chunks"


class VectorRAG:
    """基于 Milvus 的向量检索 RAG"""

    def __init__(self):
        self.embeddings = OpenAIEmbeddings(
            model=config.embedding_model,
            api_key=config.siliconflow_api_key,
            base_url=config.siliconflow_base_url,
        )
        self._vector_store: Optional[Milvus] = None
        self._connected = False

    def connect(self) -> bool:
        """连接 Milvus"""
        try:
            connections.connect(
                alias="default",
                host=config.milvus_host,
                port=config.milvus_port,
            )
            collections = utility.list_collections()
            print(f"[VectorRAG] Milvus 连接成功, 已有集合: {collections}")
            self._connected = True
            return True
        except Exception as e:
            print(f"[VectorRAG] Milvus 连接失败: {e}")
            print("[VectorRAG] 请确保 Docker Desktop 中 Milvus 已启动 (端口 19530)")
            return False

    def disconnect(self):
        """断开 Milvus 连接"""
        if self._connected:
            connections.disconnect("default")
            self._connected = False

    def build_from_documents(self, documents: list[Document]) -> bool:
        """将简历分块向量化并存入 Milvus"""
        if not self._connected:
            print("[VectorRAG] 未连接 Milvus，跳过构建")
            return False

        if not documents:
            print("[VectorRAG] 文档列表为空")
            return False

        try:
            if utility.has_collection(COLLECTION_NAME):
                utility.drop_collection(COLLECTION_NAME)
                print(f"[VectorRAG] 已删除旧集合 {COLLECTION_NAME}")

            print(f"[VectorRAG] 开始向量化 {len(documents)} 个文档块...")

            self._vector_store = Milvus.from_documents(
                documents=documents,
                embedding=self.embeddings,
                collection_name=COLLECTION_NAME,
                connection_args={
                    "host": config.milvus_host,
                    "port": config.milvus_port,
                },
                index_params={
                    "index_type": "HNSW",
                    "metric_type": "COSINE",
                    "params": {"M": 16, "efConstruction": 200},
                },
                drop_old=True,
            )

            print(f"[VectorRAG] 向量化完成, 集合: {COLLECTION_NAME}")
            return True

        except Exception as e:
            print(f"[VectorRAG] 构建失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def search(self, query: str, top_k: int = 3) -> list[Document]:
        """语义检索"""
        if not self._vector_store:
            if self._connected and utility.has_collection(COLLECTION_NAME):
                print("[VectorRAG] 从已有集合加载...")
                self._vector_store = Milvus(
                    embedding_function=self.embeddings,
                    collection_name=COLLECTION_NAME,
                    connection_args={
                        "host": config.milvus_host,
                        "port": config.milvus_port,
                    },
                )
            else:
                print("[VectorRAG] 向量库未初始化，请先调用 build_from_documents")
                return []

        try:
            results = self._vector_store.similarity_search(query, k=top_k)
            print(f"[VectorRAG] 检索到 {len(results)} 个相关文档块")
            for i, doc in enumerate(results):
                preview = doc.page_content[:80].replace("\n", " ")
                print(f"  [{i+1}] {preview}...")
            return results
        except Exception as e:
            print(f"[VectorRAG] 检索失败: {e}")
            return []

    @staticmethod
    def compare_search(keyword_results: list[Document], vector_results: list[Document]):
        """对比关键词匹配 vs 向量检索的结果"""
        print("\n" + "=" * 60)
        print("检索结果对比")
        print("=" * 60)

        print(f"\n[关键词匹配] 返回 {len(keyword_results)} 个结果:")
        for i, doc in enumerate(keyword_results):
            print(f"  [{i+1}] {doc.page_content[:100]}...")

        print(f"\n[向量检索] 返回 {len(vector_results)} 个结果:")
        for i, doc in enumerate(vector_results):
            print(f"  [{i+1}] {doc.page_content[:100]}...")

        print("=" * 60)

    def get_stats(self) -> dict:
        """获取向量库状态"""
        if not self._connected:
            return {"connected": False, "message": "Milvus 未连接"}

        try:
            if utility.has_collection(COLLECTION_NAME):
                from pymilvus import Collection
                col = Collection(COLLECTION_NAME)
                col.load()
                return {
                    "connected": True,
                    "collection": COLLECTION_NAME,
                    "num_entities": col.num_entities,
                    "index_type": "HNSW",
                    "metric_type": "COSINE",
                }
            return {"connected": True, "collection": None}
        except Exception as e:
            return {"connected": True, "error": str(e)}


# 全局实例
vector_rag = VectorRAG()
