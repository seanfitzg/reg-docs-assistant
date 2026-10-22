# The answer is redacted using the query's PII detections, not by scanning the answer

Redaction (ADR-0008) takes the matches `classify` found in the query and uses them twice: to replace the spans in the stored query, and to replace any echo of the same values in the stored answer. The answer is never run through the detector itself.

Scanning the answer was rejected because the answer legitimately quotes source text. A regulator's contact email or phone number in a retrieved Chunk is public, and a second detection pass would redact it, damaging a correct answer to protect nothing. It would also make the Flag and the redaction disagree: `pii_detected` is raised from the query, so an answer-only match would redact with no Flag to explain it.

The cost is two known gaps: PII the model writes that the user never supplied is not caught, and an echo the model reformats (`0871234567` for `087 123 4567`) is missed. Both are documented in the Track B README. If they matter, the fix is a separate, measured change, such as normalising values before matching.
