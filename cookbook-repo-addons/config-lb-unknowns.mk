# configuration file for running the impresso-ocr-qa-unigram pipeline in
# --verbose-output mode for collecting unknowns for German
# CONFIG_LOCAL_MAKE=cookbook-repo-addons/config-lb-unknowns.mk  make all
NEWSPAPER ?= lunion
LANGUAGE ?= lb
S3_BUCKET_OCRQA ?= 40-processed-data-sandbox
PROCESS_LABEL_OCRQA ?= ocrqalexicon
OCRQA_LANGUAGES_OPTION ?= lb
OCRQA_BLOOMFILTERS_OPTION ?= hf://impresso-project/OCR-quality-assessment-unigram/ocrqa-wp_v1.0.5-lbr.bloom 
OCRQA_VERBOSE_OUTPUT_OPTION ?= --verbose-output
