#!/usr/bin/env python
"""Train the Stage 2 LoRA NER model (Section 4.2 / 5.4).

Two-stage curriculum: Stage 1 trains on clean synthetic data, Stage 2
continues on the adversarially augmented mixture (Section 4.2, paragraph 3).
Requires the `ml` extra (`pip install -e ".[ml]"`) and a GPU is strongly
recommended for realistic training times.

This script is the reference training loop referenced by the paper's
Reproducibility and Data Provenance Statement (Section 5.5); running it to
completion and pointing scripts/run_adversarial_eval.py at the resulting
checkpoint is how the paper's illustrative Tables 4-7 get replaced with
measured results.

Example:
    python scripts/train_lora.py --config configs/lora_config.yaml
"""

from __future__ import annotations

import argparse
import json

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


def _load_config(path: str) -> dict:
    if yaml is None:
        raise ImportError("PyYAML is required to load config files: pip install pyyaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_jsonl_dataset(path: str):
    """Load a JSONL corpus (as produced by corpus_generator.write_jsonl) and
    convert character-offset entity annotations to BIO tag sequences aligned
    with the tokenizer's fast offset mapping. Requires the `ml` extra."""
    from arenredact.neural_ner import LABEL2ID, LoraNERConfig, load_tokenizer

    tokenizer = load_tokenizer(LoraNERConfig())
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))

    examples = []
    for rec in records:
        enc = tokenizer(rec["text"], return_offsets_mapping=True, truncation=True, max_length=256)
        offsets = enc.pop("offset_mapping")
        labels = ["O"] * len(offsets)
        for ent in rec["entities"]:
            first = True
            for i, (start, end) in enumerate(offsets):
                if start == end:
                    continue
                if start >= ent["start"] and end <= ent["end"]:
                    labels[i] = f"{'B' if first else 'I'}-{ent['entity_type']}"
                    first = False
        enc["labels"] = [LABEL2ID.get(lbl, LABEL2ID["O"]) for lbl in labels]
        examples.append(enc)
    return examples


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/lora_config.yaml")
    args = parser.parse_args(argv)

    cfg = _load_config(args.config)

    from arenredact.neural_ner import LoraNERConfig, build_lora_model, load_tokenizer

    lora_cfg = LoraNERConfig(
        base_model=cfg["base_model"],
        lora_r=cfg["lora"]["r"],
        lora_alpha=cfg["lora"]["alpha"],
        lora_dropout=cfg["lora"]["dropout"],
        target_modules=tuple(cfg["lora"]["target_modules"]),
        max_seq_length=cfg["training"]["max_seq_length"],
    )

    model = build_lora_model(lora_cfg)
    tokenizer = load_tokenizer(lora_cfg)
    model.print_trainable_parameters()

    train_examples = _load_jsonl_dataset(cfg["data"]["train_path"])
    val_examples = _load_jsonl_dataset(cfg["data"]["val_path"])

    from transformers import DataCollatorForTokenClassification, Trainer, TrainingArguments

    training_args = TrainingArguments(
        output_dir=cfg["output"]["checkpoint_dir"],
        num_train_epochs=cfg["training"]["stage1_epochs"],
        per_device_train_batch_size=cfg["training"]["batch_size"],
        learning_rate=cfg["training"]["learning_rate"],
        weight_decay=cfg["training"]["weight_decay"],
        warmup_ratio=cfg["training"]["warmup_ratio"],
        seed=cfg["training"]["seed"],
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model=cfg["output"]["metric_for_best"],
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_examples,
        eval_dataset=val_examples,
        data_collator=DataCollatorForTokenClassification(tokenizer),
    )

    print("Stage 1: training on clean synthetic data...")
    trainer.train()

    # Stage 2: continue on the adversarially augmented mixture, if provided.
    adv_path = cfg["data"].get("stage2_adversarial_path")
    if adv_path:
        print("Stage 2: continuing on adversarially augmented data...")
        adv_examples = _load_jsonl_dataset(adv_path)
        trainer.train_dataset = adv_examples
        training_args.num_train_epochs = cfg["training"]["stage2_epochs"]
        trainer.train(resume_from_checkpoint=False)

    best_dir = f"{cfg['output']['checkpoint_dir']}/checkpoint-best"
    trainer.save_model(best_dir)
    tokenizer.save_pretrained(best_dir)
    print(f"Saved best checkpoint to {best_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
