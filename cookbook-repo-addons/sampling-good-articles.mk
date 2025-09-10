# Code to sample documents with good OCR
# Usage: make sample-ocr


sample-files: $(BUILD_DIR)/sampling/ocrqa-highscores-de.jsonl \
			  $(BUILD_DIR)/sampling/ocrqa-highscores-fr.jsonl \
			  $(BUILD_DIR)/sampling/ocrqa-highscores-lb.jsonl

sampled-files: $(BUILD_DIR)/sampling/ocrqa-highscores-data-de.jsonl.bz2

$(BUILD_DIR)/sampling/ocrqa-highscores-%.jsonl:
	@mkdir -p $(dir $@)
	python3 cookbook/lib/s3_sampler.py \
		--s3-prefix s3://42-processed-data-final/ocrqa/ocrqa-ocrqa-wp_v1.0.6_v1-0-0/ \
		--output $@ \
		--filter-expr 'select(.ocrqa_unk_type_ratio > 0.95 and .lg == "$*" and .subtokens > 100)' \
		--transform-expr '{ci_id: .ci_id, lg: .lg, ocrqa: .ocrqa_unk_type_ratio, subtokens:.subtokens}' \
		--group-by-expr '.ci_id | split("-") | .[0] + "-" + .[1]' \
		--max-samples-per-group 20 \
		--record-id-field ci_id \
		--random-seed 42 \
		--log-level INFO \
		--output $@


$(BUILD_DIR)/sampling/ocrqa-highscores-data-%.jsonl.bz2: $(BUILD_DIR)/sampling/ocrqa-highscores-%.jsonl
	python3 cookbook/lib/s3_compiler.py \
		--input-file $< \
		-o $@ \
		--id-field ci_id \
		--include-from-input ci_id ocrqa lg subtokens\
		--transform-expr '{id: .ci_id, text: .ft}' \
		--s3-prefix s3://22-rebuilt-final/ \
		--log-level DEBUG
