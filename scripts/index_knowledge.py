"""知识索引脚本：将 knowledge/ 目录下的文档索引到 Qdrant"""

import sys
import os

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv

load_dotenv()

from agentlab.rag import RAGPipeline


def main():
    knowledge_dir = os.path.join(os.path.dirname(__file__), "..", "knowledge")
    knowledge_dir = os.path.abspath(knowledge_dir)

    print(f"开始索引: {knowledge_dir}")
    print("正在加载 embedding 模型 (首次运行会下载，请稍候)...")

    pipeline = RAGPipeline()

    print(f"Embedding 维度: {pipeline.embedding.dimension}")
    print("正在切分文档并向量化...")

    result = pipeline.index(knowledge_dir)

    print(f"\n索引完成:")
    print(f"  文档数: {result['documents']}")
    print(f"  切块数: {result['chunks']}")
    print(f"  向量库点数: {pipeline.vector_store.count()}")


if __name__ == "__main__":
    main()
