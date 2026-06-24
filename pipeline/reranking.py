import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

class CrossEncoderReranker:
    def __init__(self, model_name="BAAI/bge-reranker-large", device=None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name).to(self.device)
        self.model.eval()

    @torch.inference_mode()
    def score(self, query, passages, max_length=512, batch_size=16):
        scores = []
        for i in range(0, len(passages), batch_size):
            batch = passages[i:i+batch_size]
            enc = self.tokenizer(
                [query]*len(batch),
                batch,
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            ).to(self.device)

            logits = self.model(**enc).logits.squeeze(-1)  # shape: (B,)
            scores.extend(logits.detach().cpu().tolist())
        return scores

    def rerank(self, query, hits, text_key="text", top_n=None, **kwargs):
        """
        hits: list[dict] each hit must have hits[i][text_key]
        returns: hits sorted by descending score, with 'rerank_score'
        """
        passages = [h[text_key] for h in hits]
        scores = self.score(query, passages, **kwargs)
        for h, s in zip(hits, scores):
            h["rerank_score"] = float(s)
        hits_sorted = sorted(hits, key=lambda x: x["rerank_score"], reverse=True)
        return hits_sorted[:top_n] if top_n else hits_sorted