"""Stage 2 — Neural NER with LoRA Fine-Tuning.

Wraps XLM-RoBERTa Base (Conneau et al., 2020) with a Low-Rank Adaptation
(LoRA; Hu et al., 2022) token-classification head, per Section 4.2. LoRA
targets the query and value projection matrices (W_q, W_v) of each
self-attention layer with rank r=8 and scaling factor alpha=16, updating
~0.1% of model parameters — chosen for computational efficiency, resistance
to overfitting on the synthetic corpus, and (per the paper's Section 6.4 /
8.2) reduced training-data memorization relative to full fine-tuning.

Requires the `ml` extra: `pip install -e ".[ml]"`.
"""

from __future__ import annotations

from dataclasses import dataclass

from arenredact.span_fusion import Span, SpanOrigin

try:
    import torch
    from peft import LoraConfig, TaskType, get_peft_model
    from transformers import (
        AutoModelForTokenClassification,
        AutoTokenizer,
        PreTrainedModel,
        PreTrainedTokenizerBase,
    )

    _ML_AVAILABLE = True
except ImportError:  # pragma: no cover — exercised only when ml extra absent
    _ML_AVAILABLE = False


#: Entity label set (BIO tagging scheme), matching Table 2 categories.
LABEL_LIST: tuple[str, ...] = (
    "O",
    "B-PERSON", "I-PERSON",
    "B-PHONE", "I-PHONE",
    "B-NATIONAL_ID", "I-NATIONAL_ID",
    "B-EMAIL", "I-EMAIL",
    "B-IBAN", "I-IBAN",
    "B-LOCATION", "I-LOCATION",
    "B-ORGANIZATION", "I-ORGANIZATION",
    "B-DATE_OF_BIRTH", "I-DATE_OF_BIRTH",
)

LABEL2ID = {label: i for i, label in enumerate(LABEL_LIST)}
ID2LABEL = {i: label for i, label in enumerate(LABEL_LIST)}

BASE_MODEL_NAME = "xlm-roberta-base"


@dataclass(frozen=True)
class LoraNERConfig:
    """Mirrors configs/lora_config.yaml — see that file for the values used
    to produce the paper's reported (target) figures, Section 5.4."""

    base_model: str = BASE_MODEL_NAME
    lora_r: int = 8
    lora_alpha: int = 16
    lora_dropout: float = 0.05
    target_modules: tuple[str, ...] = ("query", "value")  # W_q, W_v projections
    max_seq_length: int = 256


def _require_ml() -> None:
    if not _ML_AVAILABLE:
        raise ImportError(
            "neural_ner.py requires the 'ml' extra: pip install -e '.[ml]' "
            "(needs torch, transformers, peft)."
        )


def build_lora_model(config: LoraNERConfig = LoraNERConfig()) -> "PreTrainedModel":
    """Construct an XLM-RoBERTa token-classification model wrapped with a
    LoRA adapter per Section 4.2. Returns an untrained (freshly adapted)
    model ready for the two-stage curriculum in `scripts/train_lora.py`."""
    _require_ml()

    base_model = AutoModelForTokenClassification.from_pretrained(
        config.base_model,
        num_labels=len(LABEL_LIST),
        id2label=ID2LABEL,
        label2id=LABEL2ID,
    )

    peft_config = LoraConfig(
        task_type=TaskType.TOKEN_CLS,
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        target_modules=list(config.target_modules),
        bias="none",
    )

    return get_peft_model(base_model, peft_config)


def load_tokenizer(config: LoraNERConfig = LoraNERConfig()) -> "PreTrainedTokenizerBase":
    _require_ml()
    return AutoTokenizer.from_pretrained(config.base_model)


class LoraNER:
    """Inference-time wrapper: text -> list[Span] with origin=NEURAL.

    Example:
        ner = LoraNER.from_checkpoint("runs/lora_xlmr/checkpoint-best")
        spans = ner.predict(normalized_text)
    """

    def __init__(self, model: "PreTrainedModel", tokenizer: "PreTrainedTokenizerBase"):
        _require_ml()
        self.model = model
        self.tokenizer = tokenizer
        self.model.eval()

    @classmethod
    def from_checkpoint(cls, checkpoint_path: str, config: LoraNERConfig = LoraNERConfig()) -> "LoraNER":
        _require_ml()
        from peft import PeftModel

        base_model = AutoModelForTokenClassification.from_pretrained(
            config.base_model,
            num_labels=len(LABEL_LIST),
            id2label=ID2LABEL,
            label2id=LABEL2ID,
        )
        model = PeftModel.from_pretrained(base_model, checkpoint_path)
        tokenizer = AutoTokenizer.from_pretrained(checkpoint_path)
        return cls(model, tokenizer)

    @torch.no_grad()
    def predict(self, text: str, score_threshold: float = 0.5) -> list[Span]:
        """Run token classification and decode BIO tags back to character-
        offset spans. Requires the tokenizer's fast (Rust) backend for
        `return_offsets_mapping`."""
        _require_ml()
        encoding = self.tokenizer(
            text,
            return_offsets_mapping=True,
            return_tensors="pt",
            truncation=True,
            max_length=256,
        )
        offset_mapping = encoding.pop("offset_mapping")[0].tolist()

        logits = self.model(**encoding).logits[0]
        probs = torch.softmax(logits, dim=-1)
        pred_ids = probs.argmax(dim=-1).tolist()
        pred_scores = probs.max(dim=-1).values.tolist()

        return self._decode_bio(text, offset_mapping, pred_ids, pred_scores, score_threshold)

    @staticmethod
    def _decode_bio(
        text: str,
        offset_mapping: list[list[int]],
        pred_ids: list[int],
        pred_scores: list[float],
        score_threshold: float,
    ) -> list[Span]:
        spans: list[Span] = []
        current: dict | None = None

        for (start, end), label_id, score in zip(offset_mapping, pred_ids, pred_scores):
            if start == end:  # special token (CLS/SEP/PAD)
                continue
            label = ID2LABEL[label_id]

            if label == "O" or score < score_threshold:
                if current is not None:
                    spans.append(current)
                    current = None
                continue

            prefix, entity_type = label.split("-", 1)
            if prefix == "B" or current is None or current["entity_type"] != entity_type:
                if current is not None:
                    spans.append(current)
                current = {"start": start, "end": end, "entity_type": entity_type, "score": score}
            else:  # "I-" continuing the same entity
                current["end"] = end
                current["score"] = min(current["score"], score)

        if current is not None:
            spans.append(current)

        return [
            Span(
                start=s["start"],
                end=s["end"],
                entity_type=s["entity_type"],
                origin=SpanOrigin.NEURAL,
                score=s["score"],
            )
            for s in spans
        ]
