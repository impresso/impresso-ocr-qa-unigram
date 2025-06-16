# OCR Quality Assessment with Bloom Filters

This project provides a script for performing OCR quality assessment using Bloom filters. It processes input text files, computes various OCR quality metrics, and outputs the results.

## Prerequisites

The build process has been tested on modern Linux and macOS systems.
Before cloning the repository, ensure that the following dependencies are installed:

```sh
# Ubuntu or Debian
sudo apt update -y && sudo apt install -y git git-lfs make
# MacOS assuming a working Homebrew installation
brew upgrade && brew install git git-lfs make
```

## Installation

1. Clone the repository:

   ```sh
   git clone --recursive https://github.com/your-repo/impresso-ocr-qa-unigram.git
   cd impresso-ocr-qa-unigram
   ```

2. Configure the installation:

   ```sh
   cp cookbook/dotenv.sample .env
   # edit .env with the s3 credentials

   ```

3. Install the required dependencies:

   ```sh
   make setup
   ```

## Usage

To run the OCR quality assessment script, use the following command:

```sh
python lib/ocrqa_bloom.py --input input.jsonl --bloomdicts bloom1.bloom bloom2.bloom --languages en fr --methods slc unk_ratio --output results.jsonl --lid langident.json
```

### Options

- `--log-file FILE`: Write log to FILE.
- `-q, --quiet`: Do not print status messages to stderr (default: False).
- `-v, --verbose-output`: Print verbose output information (default: False).
- `-C, --single_letter_cost`: Cost for an infrequent single char (default: 0.7).
- `-S, --single_symbol_cost`: Cost for an infrequent symbol char (default: 0.3).
- `-l, --languages`: Language iso-2-letter codes (must match the sequence of provided bloom dictionaries).
- `--input`: Input JSONL files (default: stdin).
- `--bloomdicts`: Paths to JSON files containing bloom dictionaries keys or Hugging Face
  Hub references. Must match the sequence of provided languages.
- `--unicode-normalization`: Unicode normalization form to apply to input text (default: NFKC).
- `--log-level`: Logging level (default: INFO).
- `--methods`: OCR QA methods to use (default: unk_type_ratio).
- `--keep-best`: Keep only the highest OCR value for a given content item using the first method in --methods (default: False).
- `--output`: Output file (default: stdout).
- `--lid`: Path to language identification file.
- `--s3-output-path`: S3 path to upload the output file after processing or check if it already exists.
- `--quit-if-s3-output-exists`: Quit if the output file already exists in the specified S3 bucket.
- `--keep-timestamp-only`: After uploading to S3, keep only the timestamp of the local output file for data efficiency.
- `--s3-output-dry-run`: Dry run which suppresses all write operations to s3 and checks whether output files on s3 exist.

### Default Method

The default method used for OCR quality assessment is `unk_type_ratio`. This method calculates the ratio of known unique subtoken types to all unique subtoken types. It provides a measure of how many unique words in the text are recognized by the Bloom filter, which can be an indicator of OCR quality.

### Example

```sh
python lib/ocrqa_bloom.py --input input.jsonl --bloomdicts hf://model_id/bloom1.bloom hf://model_id/bloom2.bloom --languages en fr --methods slc unk_ratio --output results.jsonl --lid langident.json
```

## Apostrophe Usage After Vowels in Historical Luxembourgish

### **1. Function of the Apostrophe**

- **Indicating long or stressed vowels**
  - _gro’ss_ → modern _grouss_
  - _se’er_ → modern _seier_
- **Marking elision or glottalization**
  - _ge’nt_, _go’f_, _go’w_ (possible sound loss or separation)
- **Clarifying pronunciation in loanwords**
  - _Unio’n_, _situatio’n_, _millio’nen_
- **Separating prefixes or morphemes**
  - _ne’deg_ → modern _néideg_
  - _we’neg_ → modern _wéineg_

### **2. Spelling Reforms and the Apostrophe**

- **Pre-1946**: Apostrophes were common after vowels, often inconsistently.
- **1946 Reform**: Reduced apostrophe use, favoring phonetic spelling.
- **1975 Reform**: Further simplification, removing unnecessary markers.
- **1999 Reform**: Apostrophes after vowels were eliminated, except in contractions (e.g., _d’Kanner_ remains, but _se’er_ → _seier_).

### **3. Summary**

The historical use of apostrophes after vowels served as a **pronunciation guide** for vowel length, stress, and borrowed words. Over time, Luxembourgish orthography **standardized and simplified**, leading to the apostrophe's removal in these contexts.

## Produce Extended output of Finding Unknown Words

```sh
# for a newspaper and Luxembourgish
CONFIG_LOCAL_MAKE=cookbook-repo-addons/config-lb-unknowns.mk  make all
```

## Contact

For any questions or issues, please contact
[simon.clematide@uzh.ch](mailto:simon.clematide@uzh.ch).

## About

### Impresso

[Impresso - Media Monitoring of the Past](https://impresso-project.ch) is an
interdisciplinary research project that aims to develop and consolidate tools for
processing and exploring large collections of media archives across modalities, time,
languages and national borders. The first project (2017-2021) was funded by the Swiss
National Science Foundation under grant
No. [CRSII5_173719](http://p3.snf.ch/project-173719) and the second project (2023-2027)
by the SNSF under grant No. [CRSII5_213585](https://data.snf.ch/grants/grant/213585))
and the Luxembourg National Research Fund under grant No. 17498891.

### Copyrights

Copyright (C) 2018-2024 The Impresso team.  
Contributors to this program include: [Maud Ehrmann](https://github.com/e-maud)

### License

This program is provided as open source under
the [GNU Affero General Public License](https://github.com/impresso/impresso-pyindexation/blob/master/LICENSE)
v3 or later.

---

<p align="center">
  <img src="https://github.com/impresso/impresso.github.io/blob/master/assets/images/3x1--Yellow-Impresso-Black-on-White--transparent.png?raw=true" width="350" alt="Impresso Project Logo"/>
</p>
