"""
OpenAI Embeddings APIを使った高精度RAG
文脈・意味・同義語を理解したベクトル検索
"""
import json
import numpy as np
from pathlib import Path
from typing import List, Dict
from openai import OpenAI


class OpenAIRAG:
    """OpenAI Embeddings APIを使ったベクトル検索RAG"""
    
    def __init__(self, knowledge_dir: Path):
        self.knowledge_dir = Path(knowledge_dir)
        self.client = OpenAI()  # 環境変数 OPENAI_API_KEY を自動読み込み
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
        
        print(f"🔄 Embeddings API でベクトル化中... ({len(self.chunks)}件)")
        
        try:
            # 全チャンクを一括でベクトル化（効率的）
            texts = [chunk['text'] for chunk in self.chunks]
            
            response = self.client.embeddings.create(
                model="text-embedding-3-small",  # 安価で高精度
                input=texts
            )
            
            self.embeddings = [item.embedding for item in response.data]
            
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
            query_response = self.client.embeddings.create(
                model="text-embedding-3-small",
                input=query
            )
            query_embedding = query_response.data[0].embedding
            
            # コサイン類似度を計算
            similarities = []
            for chunk_embedding in self.embeddings:
                similarity = self._cosine_similarity(query_embedding, chunk_embedding)
                similarities.append(similarity)
            
            # スコアの高い順にソート
            top_indices = np.argsort(similarities)[-top_k:][::-1]
            
            # 結果を返す
            results = []
            for idx in top_indices:
                chunk = self.chunks[idx].copy()
                chunk['score'] = float(similarities[idx])  # スコアを追加
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
    
    def format_context(self, chunks: List[Dict]) -> str:
        """検索結果を文字列に整形"""
        if not chunks:
            return ""
        
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            text = chunk.get('text', '')
            chunk_id = chunk.get('id', '?')
            score = chunk.get('score', 0.0)
            
            context_parts.append(
                f"[参考情報 {i}] (ID: {chunk_id}, 関連度: {score:.2f})\n{text}"
            )
        
        return "\n\n".join(context_parts)
