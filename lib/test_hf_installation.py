#!/usr/bin/env python3
import argparse
import os
from typing import List, Optional, Sequence
from huggingface_hub import hf_hub_download
import logging
from ocrqa_bloom import split_hf_path
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)-15s %(filename)s:%(lineno)d %(levelname)s: %(message)s",
    force=True,
)


def parse_arguments(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        args: Command-line arguments (uses sys.argv if None)

    Returns:
        argparse.Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(
        usage="%(prog)s [OPTIONS]",
        description="test huggingface hub download",
        epilog="Contact simon.clematide@uzh.ch",
    )
    parser.add_argument(
        "-b",
        "--bloomdicts",
        dest="bloomdicts",
        nargs="+",
        help=(
            "Paths to JSON files containing bloom dictionaries keys (default:"
            " %(default)s)"
        ),
    )
    return parser.parse_args(args)


def main(args: Optional[Sequence[str]] = None) -> None:
    """Main function to run the OCR QA process.

    Args:
        args: Command-line arguments (uses sys.argv if None)
    """
    options: argparse.Namespace = parse_arguments(args)
    print(f"OPTIONS {options}")
    for bloomdict in options.bloomdicts:
        if bloomdict.startswith("hf://"):
            model_id, filename = split_hf_path(bloomdict)
            logging.info(
                "Downloading model from Hugging Face Hub (or cache): model_id: %s"
                " filename: %s",
                model_id,
                filename,
            )
            # Authenticate with Hugging Face Hub if necessary
            token = os.getenv("HF_API_TOKEN")
            print(f"TOKEN {token}")
            local_path = hf_hub_download(
                repo_id=model_id, filename=filename, use_auth_token=token
            )
            logging.info(f"DOWNLOADED {local_path}")
        else:
            logging.info(f"CHECKED {bloomdict}")


if __name__ == "__main__":
    main()
