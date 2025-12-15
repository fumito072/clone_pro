"""
Google Gemini Embeddings APIを使った高精度RAG
文脈・意味・同義語を理解したベクトル検索
OpenAI Embeddings APIと互換性のあるインターフェース
"""
import json
import numpy as np
from pathlib import Path
from typing import List, Dict
import google.generativeai as genai


class GeminiRAG:
    """Google Gemini Embeddings APIを使ったベクトル検索RAG"""
    
    def __init__(self, knowledge_dir: Path):
        self.knowledge_dir = Path(knowledge_dir)
        # Gemini APIは既にgenai.configure()で設定済みを想定
        self.chunks: List[Dict] = []
        self.embeddings: List[List[float]] = []
        
        self._load_knowledge()
        self._build_embeddings()
    
    def _load_knowledge(self):
        """JSONLファイルからナレッジを読み込み"""
        if not self.knowledge_dir.exists():
            print(f"⚠️  ナレッジディレクトリが見つかりません: {self.knowledge_dir}")
            return
        
        json_files = list(self.knowledge_dir.glob("*.json")) + list(self.knowledge_dir.glob("*.jsonl"))
        if not json_files:
            print(f"⚠️  JSONファイルが見つかりません: {self.knowledge_dir}")
            return
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    # JSONL形式を想定（1行1JSON）
                    for line in f:
                        line = line.strip()
                        if line:
                            chunk = json.loads(line)
                            self.chunks.append(chunk)
            except Exception as e:
                print(f"⚠️  {json_file.name}の読み込みエラー: {e}")
        
        print(f"✅ ナレッジベース読み込み完了: {len(self.chunks)}件")
    
    def _build_embeddings(self):
        """全チャンクをベクトル化（初回のみ）"""
        if not self.chunks:
            return
        
        print(f"🔄 Gemini Embeddings でベクトル化中... ({len(self.chunks)}件)")
        
        try:
            # 全チャンクをベクトル化
            texts = [chunk['text'] for chunk in self.chunks]
            
            # Gemini Embeddings APIを使用
            # models/text-embedding-004 は最新の埋め込みモデル
            # 768次元、日本語対応、無料枠が大きい
            for text in texts:
                result = genai.embed_content(
                    model="models/text-embedding-004",
                    content=text,
                    task_type="retrieval_document"  # 文書検索用
                )
                self.embeddings.append(result['embedding'])
            
            print(f"✅ ベクトル化完了: {len(self.embeddings)}件")
            print(f"📊 ベクトル次元: {len(self.embeddings[0])}次元")
            
        except Exception as e:
            print(f"❌ ベクトル化エラー: {e}")
            self.embeddings = []
    
    def search(self, query: str, top_k: int = 3) -> List[Dict]:
        """
        意味ベースでベクトル検索
        
        文脈・意味・同義語を理解した検索:
        - "どうして医学部を辞めたの？" と "医学部退学の理由" が同じ意味と認識
        - "猫飼ってる？" と "猫を2匹飼育" が一致
        - "将来何がしたい？" と "最終ビジョン" が関連
        
        Args:
            query: 検索クエリ
            top_k: 返す最大件数
        
        Returns:
            関連するチャンクのリスト（スコアが高い順）
        """
        if not self.chunks or not self.embeddings:
            return []
        
        try:
            # クエリをベクトル化
            query_result = genai.embed_content(
                model="models/text-embedding-004",
                content=query,
                task_type="retrieval_query"  # クエリ用
            )
            query_embedding = query_result['embedding']
            
            # コサイン類似度を計算
            similarities = []
            for doc_embedding in self.embeddings:
                similarity = self._cosine_similarity(query_embedding, doc_embedding)
                similarities.append(similarity)
            
            # スコアが高い順にソート
            ranked_indices = np.argsort(similarities)[::-1][:top_k]
            
            results = []
            for idx in ranked_indices:
                chunk = self.chunks[idx].copy()
                chunk['score'] = float(similarities[idx])
                results.append(chunk)
            
            return results
            
        except Exception as e:
            print(f"❌ 検索エラー: {e}")
            return []
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """コサイン類似度を計算"""
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def format_context(self, search_results: List[Dict], max_length: int = 1000) -> str:
        """
        検索結果をLLMプロンプト用のコンテキストに整形
        
        Args:
            search_results: searchメソッドの結果
            max_length: 最大文字数
        
        Returns:
            整形されたコンテキスト文字列
        """
        if not search_results:
            return ""
        
        context_parts = []
        total_length = 0
        
        for i, result in enumerate(search_results, 1):
            text = result['text']
            score = result.get('score', 0)
            
            # スコアが低すぎる（関連性が薄い）場合はスキップ
            if score < 0.3:
                continue
            
            part = f"[参考{i}] {text}"
            part_length = len(part)
            
            if total_length + part_length > max_length:
                break
            
            context_parts.append(part)
            total_length += part_length
        
        return "\n\n".join(context_parts)


# 使用例
if __name__ == "__main__":
    import os
    
    # Gemini API設定
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
    
    # RAG初期化
    knowledge_dir = Path(__file__).parent / "knowledge" / "narisawa"
    rag = GeminiRAG(knowledge_dir)
    
    # 検索テスト
    test_queries = [
        "医学部を辞めた理由は？",
        "猫を飼っていますか？",
        "将来の夢は？"
    ]
    
    for query in test_queries:
        print(f"\n🔍 クエリ: {query}")
        results = rag.search(query, top_k=2)
        for i, result in enumerate(results, 1):
            print(f"  [{i}] スコア: {result['score']:.3f}")
            print(f"      {result['text'][:100]}...")
