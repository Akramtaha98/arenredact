# Annotation guidelines: structured identifiers in Arabic-English text (v1.0)

Purpose: build an independently annotated evaluation set for PHONE, EMAIL, IBAN and NATIONAL_ID spans. The detector authors must NOT annotate or adjudicate this set. Use at least two bilingual annotators who have not seen the detector's output.

## What to mark
- PHONE: any telephone number, in any format: with "+" or "00" country prefix, parentheses, hyphens, dots, spaces, Arabic-Indic, extended Arabic-Indic or fullwidth digits, and local numbers without a country code.
- EMAIL: an e-mail address, including obfuscated spellings that a human reads as an address ("name [at] domain.com" is marked from the first to the last character of the address).
- IBAN: an International Bank Account Number in compact or grouped form, any case.
- NATIONAL_ID: a national, civil, resident (iqama) or similar identity number, when the surrounding text says what it is. A bare digit string with no indication that it is an identity number is NOT marked.
- Mark the identifier only, not the label words ("National ID:") around it. Include internal separators inside the span. Do not include trailing punctuation.
- If a string is an identifier of a real or plausible person/organisation but of another type (card number, passport number), do not mark it; write OTHER_PII in the note column.

## What not to mark
Dates, prices, quantities, order/tracking/reference numbers, ISBNs, coordinates, IP addresses, years, page numbers, product codes.

## Procedure
1. Each annotator labels `sample_for_annotation.csv` independently, writing spans to their own copy of `annotations_template.csv` (columns: sentence_id, start, end, label, note). Offsets are character offsets (0-based, end exclusive) into the `text` column exactly as given.
2. Run `python annotation/agreement.py annotator_A.csv annotator_B.csv sample_for_annotation.csv`. It reports character-level Cohen's kappa, per-type span F1 between annotators, and lists every disagreement.
3. A third senior annotator adjudicates each disagreement and records the decision in `adjudication_log.csv` (sentence_id, final spans, reason). Report kappa BEFORE adjudication and the share of items changed by adjudication.
4. Freeze the adjudicated set (record its SHA-256), then run the frozen detector once.

## Reporting requirements
Number of annotators, their qualifications, kappa and span F1 before adjudication, number of adjudicated items, and the exact guideline version.
