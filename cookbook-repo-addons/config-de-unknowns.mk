# configuration file for running the impresso-ocr-qa-unigram pipeline in
# --verbose-output mode for collecting unknowns for German
# pipenv shell; CONFIG_LOCAL_MAKE=cookbook-repo-addons/config-de-unknowns.mk make all

NEWSPAPER ?= DTT
LANGUAGE ?= de
S3_BUCKET_OCRQA ?= 40-processed-data-sandbox
PROCESS_LABEL_OCRQA ?= ocrqalexicon
OCRQA_LANGUAGES_OPTION ?= de
OCRQA_BLOOMFILTERS_OPTION ?= hf://impresso-project/OCR-quality-assessment-unigram/ocrqa-wp_v1.0.6-de.bloom 
OCRQA_VERBOSE_OUTPUT_OPTION ?= --verbose-output
OCRQA_MIN_SUBTOKENS_OPTION := --min-subtokens 10

MODEL_ID_OCRQA := wp_v1.0.6
