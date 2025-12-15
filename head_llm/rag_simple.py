"""
シンプルなRAG実装 - JSONファイルベース
外部DBなし、JSONLファイルから知識を読み込んで検索
"""
import json
import re
from pathlib import Path
from typing import List, Dict, Tuple


class SimpleRAG:
    """JSON形式のナレッジベースを使ったシンプルなRAG"""
    
    def __init__(self, knowledge_dir: Path):
        """
        RAGシステムを初期化
        
        Args:
            knowledge_dir: ナレッジファイル（*.json）が格納されているディレクトリ
        """
        self.knowledge_dir = Path(knowledge_dir)
        self.chunks: List[Dict] = []
        self._load_knowledge()
    
    def _load_knowledge(self):
        """JSONLファイルからナレッジを読み込み"""
        if not self.knowledge_dir.exists():
            print(f"⚠️  [RAG] ナレッジディレクトリが見つかりません: {self.knowledge_dir}")
            return
        
        json_files = list(self.knowledge_dir.glob("*.json"))
        if not json_files:
            print(f"⚠️  [RAG] JSONファイルが見つかりません: {self.knowledge_dir}")
            return
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    # JSONL形式を想定（1行1JSON）
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if line:
                            try:
                                chunk = json.loads(line)
                                self.chunks.append(chunk)
                            except json.JSONDecodeError as e:
                                print(f"⚠️  [RAG] {json_file.name}:{line_num} JSON解析エラー: {e}")
            except Exception as e:
                print(f"⚠️  [RAG] {json_file.name}の読み込みエラー: {e}")
        
        print(f"✅ [RAG] ナレッジベース読み込み完了: {len(self.chunks)}件")
    
    def _tokenize(self, text: str) -> set:
        """
        テキストをトークン化（簡易版）
        
        Args:
            text: トークン化するテキスト
        
        Returns:
            トークンのセット
        """
        # ひらがな・カタカナ・漢字・英数字を抽出
        tokens = re.findall(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\w]+', text.lower())
        return set(tokens)
    
    def search(self, query: str, top_k: int = 3, min_score: float = 0.0) -> List[Dict]:
        """
        シンプルなキーワードマッチングで関連チャンクを検索
        
        Args:
            query: 検索クエリ
            top_k: 返す最大件数
            min_score: 最小スコア（これ以下は除外）
        
        Returns:
            関連するチャンクのリスト
        """
        if not self.chunks:
            return []
        
        # クエリをトークン化
        query_tokens = self._tokenize(query)
        
        if not query_tokens:
            return []
        
        # 各チャンクとのスコアを計算
        scored_chunks: List[Tuple[float, Dict]] = []
        
        for chunk in self.chunks:
            text = chunk.get('text', '')
            text_tokens = self._tokenize(text)
            
            if not text_tokens:
                continue
            
            # Jaccard類似度（集合の類似度）
            intersection = query_tokens & text_tokens
            union = query_tokens | text_tokens
            score = len(intersection) / len(union) if union else 0
            
            if score > min_score:
                scored_chunks.append((score, chunk))
        
        # スコア順にソート（降順）
        scored_chunks.sort(reverse=True, key=lambda x: x[0])
        
        # Top-Kを返す
        top_results = scored_chunks[:top_k]
        
        if top_results:
            print(f"💡 [RAG] 検索ヒット: {len(top_results)}件（スコア: {top_results[0][0]:.3f}〜{top_results[-1][0]:.3f}）")
        
        return [chunk for score, chunk in top_results]
    
    def format_context(self, chunks: List[Dict]) -> str:
        """
        検索結果を文字列に整形
        
        Args:
            chunks: 検索結果のチャンクリスト
        
        Returns:
            整形されたコンテキスト文字列
        """
        if not chunks:
            return ""
        
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            text = chunk.get('text', '')
            date = chunk.get('date', '')
            chunk_id = chunk.get('chunk_id', '')
            speaker = chunk.get('speaker', '')
            
            # 発言者と日付情報を含める
            metadata = []
            if speaker:
                metadata.append(f"発言者: {speaker}")
            if date:
                metadata.append(f"日付: {date}")
            if chunk_id:
                metadata.append(f"ID: {chunk_id}")
            
            metadata_str = ", ".join(metadata) if metadata else "情報なし"
            
            context_parts.append(
                f"【参考情報 {i}】({metadata_str})\n{text}"
            )
        
        return "\n\n".join(context_parts)
    
    def get_stats(self) -> Dict:
        """
        ナレッジベースの統計情報を取得
        
        Returns:
            統計情報の辞書
        """
        if not self.chunks:
            return {
                "total_chunks": 0,
                "speakers": [],
                "dates": []
            }
        
        speakers = set()
        dates = set()
        
        for chunk in self.chunks:
            if 'speaker' in chunk:
                speakers.add(chunk['speaker'])
            if 'date' in chunk:
                dates.add(chunk['date'])
        
        return {
            "total_chunks": len(self.chunks),
            "speakers": sorted(list(speakers)),
            "dates": sorted(list(dates))
        }
