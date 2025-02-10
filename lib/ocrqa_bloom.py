#!/usr/bin/env python3
"""
OCR Quality Assessment Inference Script with Bloom Filter

This script performs OCR quality assessment using Bloom filters. It processes input text files, computes various OCR quality metrics, and outputs the results.

Usage:
    python ocrqa_bloom.py --input input.jsonl --bloomdicts bloom1.bloom bloom2.bloom --languages en fr --methods slc unk_ratio --output results.jsonl --lid langident.json

Options:
    --log-file FILE           Write log to FILE
    -q, --quiet               Do not print status messages to stderr (default: False)
    -v, --verbose-output      Print verbose output information (default: False)
    -C, --single_letter_cost  Cost for an infrequent single char (default: 0.7)
    -S, --single_symbol_cost  Cost for an infrequent symbol char (default: 0.3)
    -l, --languages           Language iso-2-letter codes (must match the number of bloom dictionaries)
    --input                   Input JSONL files (default: stdin)
    --bloomdicts              Paths to JSON files containing bloom dictionaries keys or Hugging Face Hub references
    --unicode-normalization   Unicode normalization form to apply to input text (default: NFKC)
    --log-level               Logging level (default: INFO)
    --methods                 OCR QA methods to use (default: unk_type_ratio)
    --keep-best               Keep only the highest OCR value for a given content item using the first method in --methods (default: False)
    --output                  Output file (default: stdout)
    --lid                     Path to language identification file
    --s3-output-path          S3 path to upload the output file after processing or check if it already exists
    --quit-if-s3-output-exists
                              Quit if the output file already exists in the specified S3 bucket
    --keep-timestamp-only     After uploading to S3, keep only the timestamp of the local output file for data efficiency
    --s3-output-dry-run       Dry run which suppresses all write operations to s3 and checks whether output files on s3 exist

Example:
    python ocrqa_bloom.py --input input.jsonl --bloomdicts bloom1.bloom bloom2.bloom --languages en fr --methods slc unk_ratio --output results.jsonl --lid langident.json
    python ocrqa_bloom.py --input input.jsonl --bloomdicts hf://model_id/bloom1.bloom hf://model_id/bloom2.bloom --languages en fr --methods slc unk_ratio --output results.jsonl --lid langident.json

Description:
    This script reads input text files in JSONL format, where each line is a JSON object containing text to be assessed. It uses Bloom filters to compute various OCR quality metrics, such as single letter cost (slc), unknown ratio (unk_ratio), and unknown type ratio (unk_type_ratio). The results are output in JSONL format.

    The script supports multiple languages and Bloom filters. The number of languages must match the number of Bloom filters provided. The --keep-best option allows keeping only the highest OCR value for a given content item using the first method specified in --methods.

    If a language identification file is provided using the --lid option, only the relevant bloomdicts will be applied based on the identified language of each content item.

    Bloom dictionaries can be specified as local file paths or as references to files in a Hugging Face Hub model directory using the "hf://" prefix.

    Logging can be configured using the --log-file and --log-level options. Verbose output can be printed using the --verbose-output option.

    The script also supports uploading the output file to an S3 bucket, with options to quit if the file already exists, keep only the timestamp of the local file, and perform a dry run to check for existing files without making any changes.

Contact:
    For any questions or issues, please contact simon.clematide@uzh.ch
"""

import logging
import collections
import argparse
import json
import sys
from smart_open import open as smart_open
from pybloomfilter import BloomFilter
from typing import List, Any, Set, Dict, Counter, Optional, Sequence, Tuple
from ocrqa_normalization import subtokens
import unicodedata
from huggingface_hub import hf_hub_download
import os
from dotenv import load_dotenv


import traceback
from s3_to_local_stamps import (
    keep_timestamp_only,
    get_s3_client,
    s3_file_exists,
    upload_file_to_s3,
    get_timestamp,
)

load_dotenv()


def read_langident(path: str) -> Dict[str, str]:
    """
    Reads language identification results from a file.

    Args:
        path (str): The path to the language identification file.

    Returns:
        Dict[str, str]: A dictionary mapping document IDs to their identified languages.
    """
    result = {}
    if path.startswith("s3://"):
        transport_params = {"client": get_s3_client()}
    else:
        transport_params = {}
    with smart_open(
        path, "r", encoding="utf-8", transport_params=transport_params
    ) as f:
        for line in f:
            try:
                contentitem = json.loads(line)
                result[contentitem["id"]] = contentitem.get("lg")
            except KeyError:
                logging.error("Problem %s", line)
    return result


def split_hf_path(hf_path: str) -> Tuple[str, str]:
    """
    Split a Hugging Face Hub path into its model ID and filename components.

    Args:
        hf_path (str): The Hugging Face Hub path in the format "hf://organization/model_id/path/to/file".

    Returns:
        Tuple[str, str]: A tuple containing the model ID (organization/model_id) and filename path.

    Examples:
        >>> split_hf_path("hf://impresso-project/OCR-quality-assessment-unigram/path/to/file.bloom")
        ('impresso-project/OCR-quality-assessment-unigram', 'path/to/file.bloom')

        >>> split_hf_path("hf://another-org/another-repo/somefile.bloom")
        ('another-org/another-repo', 'somefile.bloom')
    """
    if not hf_path.startswith("hf://"):
        raise ValueError("Invalid Hugging Face Hub path format")

    # Remove the hf:// prefix
    path = hf_path[5:]

    # Split into components
    parts = path.split("/", 2)
    if len(parts) < 3:
        raise ValueError(
            "Invalid Hugging Face Hub path format - must include"
            " organization/model_id/filename"
        )

    # First two components form the model ID, the rest is the filename path
    model_id = f"{parts[0]}/{parts[1]}"
    filename = parts[2]

    return (model_id, filename)


class OcrQABloomProcessor(object):
    """OCR Quality Assessment Processor using Bloom Filter."""

    def __init__(self, options: Any) -> None:
        self.options: Any = options
        if len(options.bloomdicts) != len(options.languages):
            raise ValueError(
                "The number of bloom dictionaries must match the number of languages."
            )
        self.bloom_filters: List[BloomFilter] = [
            self.load_bloom_filter(bloomdict) for bloomdict in options.bloomdicts
        ]
        self.languages: List[str] = options.languages
        self.lang_ident_data: Dict[str, str] | None = (
            read_langident(self.options.lid) if self.options.lid else None
        )
        self.single_chars: Set[str] = set("àndl")
        self.ocrqa_stats: List[float] = []
        self.unks: Dict[str, Counter[str]] = {
            bloomdict: collections.Counter() for bloomdict in options.bloomdicts
        }
        self.logfile: Optional[str] = options.log_file
        self.quiet: bool = options.quiet
        self.verbose_output: bool = options.verbose_output
        self.single_letter_cost: float = options.single_letter_cost
        self.single_symbol_cost: float = options.single_symbol_cost
        self.input: Optional[List[str]] = options.input
        self.unicode_normalization: Optional[str] = options.unicode_normalization
        self.log_level: str = options.log_level
        self.methods: List[str] = options.methods
        self.timestamp: str = get_timestamp()
        self.min_subtokens: int = options.min_subtokens
        self.git_version = (
            self.options.git_version
            if self.options.git_version
            else os.environ.get("GIT_VERSION", None)
        )
        self.S3_CLIENT = (
            get_s3_client()
            if any(input_file.startswith("s3://") for input_file in self.input)
            or str(self.options.lid).startswith("s3://")
            else None
        )
        self.lang_stats: Dict[str, int] = collections.defaultdict(int)
        if not options.s3_output_dry_run:
            # Check if the output file already exists in S3 and avoid lengthy processing
            if self.options.quit_if_s3_output_exists and (
                s3out := self.options.s3_output_path
            ):
                if s3_file_exists(self.S3_CLIENT, s3out):
                    logging.warning(
                        "%s exists. Exiting without processing %s",
                        s3out,
                        self.input,
                    )
                    exit(3)
                else:
                    logging.info(
                        "%s does not exist. Proceeding with processing.", s3out
                    )

    def load_bloom_filter(self, bloomdict: str) -> BloomFilter:
        """
        Load a Bloom filter from a local file or Hugging Face Hub.

        This method supports loading Bloom filters from two sources:
        1. Local file paths.
        2. Hugging Face Hub model directories using the "hf://" prefix.

        Args:
            bloomdict (str): The path to the Bloom filter file. This can be a local file path
                             or a Hugging Face Hub reference in the format "hf://organization/repository/filename".

        Returns:
            BloomFilter: The loaded Bloom filter object.

        Raises:
            ValueError: If the bloomdict path is invalid or the file cannot be loaded.

        """
        if bloomdict.startswith("hf://"):
            model_id, filename = split_hf_path(bloomdict)
            logging.info(
                "Downloading model from Hugging Face Hub (or cache): model_id: %s"
                " filename: %s",
                model_id,
                filename,
            )
            # Authenticate with Hugging Face Hub if necessary
            # token = os.getenv("HF_API_TOKEN")
            local_path = hf_hub_download(
                repo_id=model_id, filename=filename  # , use_auth_token=token
            )
            return BloomFilter.open(local_path)
        else:
            return BloomFilter.open(bloomdict)
        logging.info("Loaded Bloom filter from %s", bloomdict)

    def get_subtokens(self, line: str) -> Dict[str, Any]:
        """Extract subtokens from the input line."""
        obj: Dict[str, Any] = json.loads(line)
        result: Dict[str, Any] = {"id": obj.get("id"), "subtokens": []}
        if "ft" in obj:
            ft: str = obj["ft"].lower()
            if self.options.unicode_normalization:
                ft = unicodedata.normalize(self.options.unicode_normalization, ft)
            result["subtokens"] = subtokens(ft, unicode_normalize=None)
        return result

    def compute_ocrqa_slc(
        self, subtoks_list: List[str], bf: BloomFilter, i: int
    ) -> float:
        """Compute OCR QA score with single letter cost."""
        counter: Counter[str] = collections.Counter()
        counter["SL"] = -len(subtoks_list) / 20
        for subtok in subtoks_list:
            if subtok in bf:
                if len(subtok) > 1 or subtok in self.single_chars:
                    counter["IV"] += 1
                else:
                    counter["SL"] += float(self.options.single_letter_cost)
            else:
                counter["OOV"] += 1
                self.unks[self.options.bloomdicts[i]][subtok] += 1
        if counter["SL"] < 0:
            counter["SL"] = 0
        if "l" not in self.options.mode:
            counter["SL"] = 0
        totalsub: float = sum(counter.values())
        if totalsub == 0:
            return 0.0
        return round(counter["IV"] / totalsub, 2)

    def compute_ocrqa_unk_ratio(
        self, subtoks_list: List[str], bf: BloomFilter
    ) -> float:
        """Compute OCR QA score as the ratio of known subtokens to all subtokens."""

        known_count: int = sum(1 for subtok in subtoks_list if subtok in bf)
        if not subtoks_list:
            return 0.0
        return round(known_count / len(subtoks_list), 2)

    def compute_ocrqa_unk_type_ratio(
        self, subtoks_list: List[str], bf: BloomFilter
    ) -> float:
        """Compute OCR QA score as the ratio of known unique subtoken types to all
        unique subtoken types."""

        unique_subtoks: Set[str] = set(subtoks_list)
        known_count: int = sum(1 for subtok in unique_subtoks if subtok in bf)
        if not unique_subtoks:
            return 0.0
        return round(known_count / len(unique_subtoks), 2)

    def process_line(self, line: str) -> List[Dict[str, Any]]:
        """Process a single line of input."""
        subtoks_info: Dict[str, Any] = self.get_subtokens(line)
        subtoks_list: List[str] = subtoks_info["subtokens"]

        if len(subtoks_list) < self.min_subtokens:
            return []

        results: List[Dict[str, Any]] = []
        best_result_index: int = -1
        best_ocrqa_value: float = -1.0
        # Treat the case where there is only one method as if keep_best is set
        keep_best_method: Optional[str] = (
            self.methods[0]
            if self.options.keep_best or len(self.methods) == 1
            else None
        )

        docid = subtoks_info["id"]
        lang = None

        if self.lang_ident_data:
            lang = self.lang_ident_data.get(docid)

        if lang:
            if lang not in self.languages:
                logging.warning(
                    "No bloomdict for language %s: content item: %s", lang, docid
                )
                return results

            lang_index = self.languages.index(lang)
            bf = self.bloom_filters[lang_index]
            result, best_ocrqa_value, best_result_index = self.compute_results(
                subtoks_info,
                subtoks_list,
                bf,
                lang,
                lang_index,
                keep_best_method,
                best_ocrqa_value,
                best_result_index,
                results,
            )
            self.lang_stats[lang] += 1
            if result:
                results.append(result)
        else:
            for lang_index, bf in enumerate(self.bloom_filters):
                lang = self.languages[lang_index]
                result, best_ocrqa_value, best_result_index = self.compute_results(
                    subtoks_info,
                    subtoks_list,
                    bf,
                    lang,
                    lang_index,
                    keep_best_method,
                    best_ocrqa_value,
                    best_result_index,
                    results,
                )
                self.lang_stats[lang] += 1
                if result:
                    results.append(result)

        if (
            self.options.keep_best or len(self.methods) == 1
        ) and best_result_index != -1:
            best_result = results[best_result_index]
            if "ocrqa_slc" in best_result:
                self.ocrqa_stats.append(best_result["ocrqa_slc"])
            elif "ocrqa_unk_ratio" in best_result:
                self.ocrqa_stats.append(best_result["ocrqa_unk_ratio"])
            elif "ocrqa_unk_type_ratio" in best_result:
                self.ocrqa_stats.append(best_result["ocrqa_unk_type_ratio"])
            results = [best_result]
        else:
            # Ensure stats are appended even if keep_best is not set
            for result in results:
                if "ocrqa_slc" in result:
                    self.ocrqa_stats.append(result["ocrqa_slc"])
                elif "ocrqa_unk_ratio" in result:
                    self.ocrqa_stats.append(result["ocrqa_unk_ratio"])
                elif "ocrqa_unk_type_ratio" in result:
                    self.ocrqa_stats.append(result["ocrqa_unk_type_ratio"])

        return results

    def compute_results(
        self,
        subtoks_info,
        subtoks_list,
        bf,
        lang,
        lang_index,
        keep_best_method,
        best_ocrqa_value,
        best_result_index,
        results,
    ) -> Tuple[Dict[str, Any], float, int]:
        """
        Compute OCR QA results for a given language and Bloom filter.

        Args:
            subtoks_info (Dict[str, Any]): Information about the subtokens.
            subtoks_list (List[str]): List of subtokens.
            bf (BloomFilter): Bloom filter for the given language.
            lang (str): Language code.
            lang_index (int): Index of the language in the languages list.
            keep_best_method (Optional[str]): Method to keep the best result.
            best_ocrqa_value (float): Current best OCR QA value.
            best_result_index (int): Index of the best result in the results list.
            results (List[Dict[str, Any]]): List of results.

        Returns:
            Tuple[Dict[str, Any], float, int]: The result dictionary, updated best OCR QA value, and updated best result index.
        """
        result: Dict[str, Any] = {
            "ci_id": subtoks_info["id"],
            "lg": lang,
            "ocrqa": None,
            "bloom": self.options.bloomdicts[lang_index],
            "subtokens": len(subtoks_list),
            "timestamp": self.timestamp,
            "git_version": self.git_version,
        }
        if self.git_version:
            result["git_version"] = self.git_version
        if "slc" in self.methods:
            ocrqa_slc: float = self.compute_ocrqa_slc(subtoks_list, bf, lang_index)
            self.ocrqa_stats.append(ocrqa_slc)
            result["ocrqa_slc"] = ocrqa_slc
            if keep_best_method == "slc" and ocrqa_slc > best_ocrqa_value:
                best_ocrqa_value = ocrqa_slc
                best_result_index = len(results)
        if "unk_ratio" in self.methods:
            ocrqa_unk_ratio: float = self.compute_ocrqa_unk_ratio(subtoks_list, bf)
            result["ocrqa_unk_ratio"] = ocrqa_unk_ratio
            if keep_best_method == "unk_ratio" and ocrqa_unk_ratio > best_ocrqa_value:
                best_ocrqa_value = ocrqa_unk_ratio
                best_result_index = len(results)
        if "unk_type_ratio" in self.methods:
            ocrqa_unk_type_ratio: float = self.compute_ocrqa_unk_type_ratio(
                subtoks_list, bf
            )
            result["ocrqa_unk_type_ratio"] = ocrqa_unk_type_ratio
            if (
                keep_best_method == "unk_type_ratio"
                and ocrqa_unk_type_ratio > best_ocrqa_value
            ):
                best_ocrqa_value = ocrqa_unk_type_ratio
                best_result_index = len(results)

        # Store the value of the first method in --methods as "ocrqa"
        first_method = self.methods[0]
        if first_method == "slc":
            result["ocrqa"] = result["ocrqa_slc"]
        elif first_method == "unk_ratio":
            result["ocrqa"] = result["ocrqa_unk_ratio"]
        elif first_method == "unk_type_ratio":
            result["ocrqa"] = result["ocrqa_unk_type_ratio"]

        if self.verbose_output:
            known_counter: Counter[str] = collections.Counter(
                subtok for subtok in sorted(subtoks_list) if subtok in bf
            )
            result["known_freq"] = known_counter
            unknown_counter: Counter[str] = collections.Counter(
                subtok for subtok in sorted(subtoks_list) if subtok not in bf
            )
            result["unk_freq"] = unknown_counter
        return result, best_ocrqa_value, best_result_index

    def run(self) -> None:
        """Run the OCR QA process."""
        input_files: List[str] = self.options.input if self.options.input else ["-"]
        output_file = (
            open(self.options.output, "w") if self.options.output else sys.stdout
        )
        for input_file in input_files:
            if input_file.startswith("s3://"):
                transport_params = {"client": get_s3_client()}
            else:
                transport_params = {}
            logging.debug("Processing %s", input_file)
            with smart_open(
                input_file, "r", encoding="utf-8", transport_params=transport_params
            ) as f:
                for line in f:
                    results: List[Dict[str, Any]] = self.process_line(line)
                    for result in results:
                        if result:
                            print(
                                json.dumps(result, ensure_ascii=False), file=output_file
                            )
        if len(self.ocrqa_stats) > 0:
            logging.info(
                "STATS-MEANOCRAQ\t%f", sum(self.ocrqa_stats) / len(self.ocrqa_stats)
            )
        else:
            logging.info("No OCRQA computed")

        for lang, count in self.lang_stats.items():
            logging.info(
                "STATS-OCRAQED-LANGUAGE %s: %d content items OCR QA-ed", lang, count
            )
        if self.options.output:
            output_file.close()

        # Upload the output file to S3 if specified
        if not self.options.s3_output_dry_run and self.options.s3_output_path:
            upload_file_to_s3(
                self.S3_CLIENT, self.options.output, self.options.s3_output_path
            )

            if self.options.keep_timestamp_only:
                keep_timestamp_only(self.options.output)
        logging.info("Finished processing %s", input_files)


def parse_arguments(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        args: Command-line arguments (uses sys.argv if None)

    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(
        usage="%(prog)s [OPTIONS]",
        description="OCR quality assessment with unigram word bloom filter",
        epilog="Contact simon.clematide@uzh.ch",
    )
    parser.add_argument(
        "--log-file", dest="log_file", help="write log to FILE", metavar="FILE"
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        dest="quiet",
        default=False,
        help="do not print status messages to stderr (default: %(default)s)",
    )
    parser.add_argument(
        "-v",
        "--verbose-output",
        action="store_true",
        dest="verbose_output",
        default=False,
        help="print verbose output information (default: %(default)s)",
    )
    parser.add_argument(
        "-C",
        "--single_letter_cost",
        action="store",
        dest="single_letter_cost",
        default=0.7,
        help="cost for an infrequent single char (default: %(default)s)",
    )
    parser.add_argument(
        "-S",
        "--single_symbol_cost",
        action="store",
        dest="single_symbol_cost",
        default=0.3,
        help="cost for an infrequent symbol char (default: %(default)s)",
    )
    parser.add_argument(
        "-l",
        "--languages",
        action="store",
        dest="languages",
        nargs="+",
        default=None,
        help=(
            "Language iso-2-letter codes (must match the number of bloom dictionaries)"
            " (default: %(default)s)"
        ),
    )
    parser.add_argument(
        "-i",
        "--input",
        dest="input",
        nargs="+",
        help="input JSONL files (default: %(default)s)",
        default=None,
    )
    parser.add_argument(
        "-b",
        "--bloomdicts",
        dest="bloomdicts",
        nargs="+",
        default=None,
        help=(
            "Paths to JSON files containing bloom dictionaries keys (default:"
            " %(default)s)"
        ),
    )
    parser.add_argument("--lid", help="Path to language identification file")
    parser.add_argument(
        "-u",
        "--unicode-normalization",
        choices=["NFC", "NFD", "NFKC", "NFKD", None],
        default="NFKC",
        help="Unicode normalization form to apply to input text (default: %(default)s)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: %(default)s)",
    )
    parser.add_argument(
        "-m",
        "--methods",
        dest="methods",
        nargs="+",
        choices=["slc", "unk_ratio", "unk_type_ratio"],
        default=["unk_type_ratio"],
        help="OCR QA methods to use (default: %(default)s)",
    )
    parser.add_argument(
        "--keep-best",
        action="store_true",
        dest="keep_best",
        default=False,
        help=(
            "keep only the highest OCR value for a given content item using the"
            " first method in --methods (default: %(default)s)"
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output",
        help="output file (default: %(default)s)",
        default=None,
    )
    parser.add_argument(
        "--s3-output-path",
        help=(
            "S3 path to upload the output file after processing or check if it already"
            " exists"
        ),
    )
    parser.add_argument(
        "--quit-if-s3-output-exists",
        action="store_true",
        help="Quit if the output file already exists in the specified S3 bucket",
    )
    parser.add_argument(
        "--keep-timestamp-only",
        action="store_true",
        help=(
            "After uploading to S3, keep only the timestamp of the local output file"
            " for data efficiency. Defaults: %(default)s"
        ),
    )
    parser.add_argument(
        "--s3-output-dry-run",
        action="store_true",
        help=(
            "Dry run which suppresses all write operations to s3 and checks whether"
            " output files on s3 exist. Implies also unsetting --keep-timestamp-only"
            " and --quit-if-s3-output-exists flag."
        ),
    )
    parser.add_argument(
        "--min-subtokens",
        type=int,
        default=10,
        help=(
            "Minimum number of subtokens required to create a value. A subtoken is a"
            " token that remains after applying some ocrqa-specific masking and"
            " splitting. (default: %(default)s)"
        ),
    )
    parser.add_argument(
        "--git-version",
        help=(
            "Set the git version to include in the output. If not set, the GIT_VERSION"
            " environment variable is used."
            "Normally the output of `git describe --tags --always` is used."
        ),
    )

    return parser.parse_args(args)


def setup_logging(log_level: str, log_file: Optional[str]) -> None:
    """Configure logging.

    Args:
        log_level: Logging level as a string
        log_file: Path to the log file
    """

    class SmartFileHandler(logging.FileHandler):
        def _open(self):
            return smart_open(self.baseFilename, self.mode, encoding="utf-8")

    handlers: List[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        handlers.append(SmartFileHandler(log_file, mode="w"))

    logging.basicConfig(
        level=log_level,
        format="%(asctime)-15s %(filename)s:%(lineno)d %(levelname)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def main(args: Optional[Sequence[str]] = None) -> None:
    """Main function to run the OCR QA process.

    Args:
        args: Command-line arguments (uses sys.argv if None)
    """
    options: argparse.Namespace = parse_arguments(args)

    setup_logging(options.log_level, options.log_file)
    logging.info("Calling OCR QA Bloom Processor with options: %s", options)
    if not options.bloomdicts:
        logging.error("WARNING: No bloom dictionaries provided; cannot perform OCR QA")
        sys.exit(1)
    try:
        processor: OcrQABloomProcessor = OcrQABloomProcessor(options)
        processor.run()
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        logging.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
    sys.exit(0)
