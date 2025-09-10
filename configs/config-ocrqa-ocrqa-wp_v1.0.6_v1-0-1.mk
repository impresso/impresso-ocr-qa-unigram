S3_BUCKET_OCRQA := 42-processed-data-final

OCRQA_BLOOMFILTERS_OPTION := hf://impresso-project/OCR-quality-assessment-unigram/ocrqa-wp_v1.0.6-de.bloom hf://impresso-project/OCR-quality-assessment-unigram/ocrqa-wp_v1.0.6-fr.bloom

OCRQA_MIN_SUBTOKENS_OPTION := --min-subtokens 10

MODEL_ID_OCRQA := wp_v1.0.6

RUN_VERSION_OCRQA := v1-0-1
S3_BUCKET_LANGIDENT := 42-processed-data-final
# soft hack for old langident path
RUN_ID_LANGIDENT := langident_v1-4-4
