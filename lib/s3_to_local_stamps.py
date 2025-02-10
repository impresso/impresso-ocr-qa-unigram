"""
This module, `s3_to_local_stamps.py`, is a utility for creating local stamp files that
mirror the structure of specified S3 objects.

The main class, `LocalStampCreator`, orchestrates the process of creating these stamp
files. It uses the boto3 library to interact with the S3 service and the os library to
create local directories and files.

The module uses environment variables to configure the S3 resource object. These
variables include the access key, secret key, and host URL for the S3 service.

The module can be run as a standalone script. It accepts command-line arguments for the
S3 bucket name, file prefix to match in the bucket, verbosity level for logging, and an
optional log- file.
"""

__author__ = "simon.clematide@uzh.ch"
__license__ = "GNU GPL 3.0 or later"

import argparse
import datetime
import logging
import fnmatch
import os
import time
import sys
from typing import Any, Tuple, Optional
import bz2
import boto3
import hashlib
import traceback
import smart_open
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

SCHEMA_BASE_URI = "https://impresso.github.io/impresso-schemas/json/"

IMPRESSO_SCHEMA = "topics.schema.json"


def calculate_md5(file_path: str, s3_client: boto3.client = None) -> str:
    """
    Calculates the MD5 checksum of a file. Supports both local and S3 paths.

    Args:
        file_path (str): The path to the file (local or S3).
        s3_client (boto3.client, optional): The S3 client to use if the file is in S3.

    Returns:
        str: The MD5 checksum of the file.
    """
    hash_md5 = hashlib.md5()

    if file_path.startswith("s3://"):
        if s3_client is None:
            raise ValueError("s3_client must be provided for S3 paths")
        bucket, key = parse_s3_path(file_path)
        obj = s3_client.get_object(Bucket=bucket, Key=key)
        for chunk in iter(lambda: obj["Body"].read(4096), b""):
            hash_md5.update(chunk)
    else:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)

    return hash_md5.hexdigest()


def have_same_md5(
    file_path1: str, file_path2: str, s3_client: boto3.client = None
) -> bool:
    """
    Compares the MD5 checksums of two files (local or S3) and returns True if they are the same, False otherwise.

    Args:
        file_path1 (str): The path to the first file (local or S3).
        file_path2 (str): The path to the second file (local or S3).
        s3_client (boto3.client, optional): The S3 client to use if any of the files are in S3.

    Returns:
        bool: True if the files have the same MD5 checksum, False otherwise.
    """
    logging.debug("Comparing MD5 checksums of %s and %s", file_path1, file_path2)
    md5_1 = calculate_md5(file_path1, s3_client)
    md5_2 = calculate_md5(file_path2, s3_client)
    return md5_1 == md5_2


def upload_with_retries(
    s3_client: boto3.client,
    local_file_path: str,
    s3_path: str,
    max_retries: int = 5,
    sleep_time: int = 3,
) -> bool:
    """
    Tries to overwrite the S3 file by first uploading a temporary file and verifying the MD5 checksum.

    Args:
        s3_client (boto3.client): The S3 client to use.
        local_file_path (str): The path to the local file.
        s3_path (str): The S3 path to the file.
        max_retries (int): The maximum number of retries if the MD5 checksum does not match.
        sleep_time (int): The number of seconds to sleep between retries.

    Returns:
        bool: True if the file was successfully overwritten, False otherwise.
    """
    bucket, key = parse_s3_path(s3_path)
    tmp_key = key + ".tmp"
    local_md5 = calculate_md5(local_file_path)

    for attempt in range(max_retries):
        try:
            # Upload the temporary file to S3
            s3_client.upload_file(local_file_path, bucket, tmp_key)
            log.info(f"Uploaded temporary file to s3://{bucket}/{tmp_key}")

            # Calculate the MD5 checksum of the uploaded temporary file
            s3_md5 = calculate_md5(f"s3://{bucket}/{tmp_key}", s3_client=s3_client)

            # Verify the MD5 checksum
            if local_md5 == s3_md5:
                # Copy the temporary file to the final destination
                s3_client.copy_object(
                    Bucket=bucket,
                    Key=key,
                    CopySource={"Bucket": bucket, "Key": tmp_key},
                    MetadataDirective="REPLACE",
                )
                log.info(
                    f"Successfully copied s3://{bucket}/{tmp_key} to"
                    f" s3://{bucket}/{key}"
                )
                s3_md5_overwritten = calculate_md5(
                    f"s3://{bucket}/{key}", s3_client=s3_client
                )
                if local_md5 == s3_md5_overwritten:
                    log.info(f"MD5 checksum verified after overwrite: {local_md5}")
                else:
                    log.error(
                        f"MD5 checksum mismatch after overwrite: local file {local_md5}"
                        f" != s3 file {s3_md5_overwritten}"
                    )
                    raise ValueError(
                        f"MD5 checksum mismatch after overwrite: s3://{bucket}/{key} is"
                        " probably corrupted."
                    )
                return True
            else:
                log.warning(
                    f"MD5 checksum mismatch: local file {local_md5} != s3 file {s3_md5}"
                )
                time.sleep(sleep_time)
        except Exception as e:
            log.error(f"An error occurred during upload attempt {attempt + 1}: {e}")
            time.sleep(sleep_time)
        finally:
            s3_client.delete_object(Bucket=bucket, Key=tmp_key)
            log.info(f"Deleted temporary file s3://{bucket}/{tmp_key}")

    log.error(
        f"Failed to overwrite s3://{bucket}/{key} after {max_retries} attempts."
        " Continuing..."
    )
    return False


def download_with_retries(
    s3_client: boto3.client,
    s3_path: str,
    local_file_path: str,
    max_retries: int = 5,
    sleep_time: int = 3,
) -> bool:
    """
    Tries to download an S3 file and verifies the MD5 checksum.

    Args:
        s3_client (boto3.client): The S3 client to use.
        s3_path (str): The S3 path to the file.
        local_file_path (str): The path to the local file.
        max_retries (int): The maximum number of retries if the MD5 checksum does not match.
        sleep_time (int): The number of seconds to sleep between retries.

    Returns:
        bool: True if the file was successfully downloaded and verified, False otherwise.
    """
    bucket, key = parse_s3_path(s3_path)
    s3_md5 = calculate_md5(s3_path, s3_client=s3_client)

    for attempt in range(max_retries):
        try:
            # Download the file from S3
            s3_client.download_file(bucket, key, local_file_path)
            log.info(f"Downloaded file to {local_file_path}")

            # Calculate the MD5 checksum of the downloaded file
            local_md5 = calculate_md5(local_file_path)

            # Verify the MD5 checksum
            if local_md5 == s3_md5:
                log.info(f"MD5 checksum verified: {local_md5}")
                return True
            else:
                log.warning(
                    f"MD5 checksum mismatch: local file {local_md5} != s3 file {s3_md5}"
                )
                time.sleep(sleep_time)
        except Exception as e:
            log.error(f"An error occurred during download attempt {attempt + 1}: {e}")
            time.sleep(sleep_time)

    log.error(
        f"Failed to download and verify s3://{bucket}/{key} after"
        f" {max_retries} attempts"
    )
    return False


def get_timestamp() -> str:
    """
    Generates a timestamp in a specific format.

    Returns:
        str: The generated timestamp.

    Example:
        >>> len(get_timestamp()) == 20
        True
    """
    timestamp = datetime.datetime.now(datetime.timezone.utc)

    return timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def keep_timestamp_only(
    input_path: str, timestamp: datetime.datetime | None = None
) -> None:
    """
    Truncates the file to zero length and updates its metadata to the UTC timestamp.

    Args:
        input_path (str): The path to the file to be truncated and timestamped.
        timestamp (datetime, optional): The UTC timestamp to set for the file's
            metadata. If not provided, the current UTC time will be used.

    Raises:
        Exception: If an error occurs during the truncation or timestamp update process.

    Example:
        >>> import tempfile
        >>> from datetime import datetime, timezone
        >>> with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        ...     tmp_file_path = tmp_file.name
        >>> keep_timestamp_only(tmp_file_path, datetime(2023, 1, 1, tzinfo=timezone.utc))
        >>> os.path.getsize(tmp_file_path) == 0
        True
        >>> os.path.getmtime(tmp_file_path) == datetime(2023, 1, 1, tzinfo=timezone.utc).timestamp()
        True
        >>> os.remove(tmp_file_path)
    """

    try:
        # Truncate the file to zero length
        with open(input_path, "w", encoding="utf-8"):
            # opening with 'w' truncates the file
            log.info("Truncating %s and setting its timestamp metadata.", input_path)

        # Use the provided timestamp or default to the current UTC time
        if timestamp is None:
            timestamp = datetime.datetime.now(datetime.timezone.utc)

        # Convert the timestamp to a Unix timestamp (seconds since epoch)
        timestamp_epoch = timestamp.timestamp()

        # Update the file's modification and access time to the specified timestamp
        os.utime(input_path, (timestamp_epoch, timestamp_epoch))

        log.info(
            "Truncated %s and timestamp set to %s.",
            input_path,
            timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    except Exception as e:
        log.error("Failed to truncate %s: %s", input_path, e)
        raise


def get_s3_client() -> "boto3.client":
    """Returns a boto3.client object for interacting with S3.

    Returns:
        boto3.client: A boto3.client object for interacting with S3.
    """
    import boto3  # noqa: E402

    boto3.setup_default_session(
        aws_access_key_id=os.getenv("SE_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("SE_SECRET_KEY"),
    )

    return boto3.client(
        "s3", endpoint_url=os.getenv("SE_HOST_URL", "https://os.zhdk.cloud.switch.ch/")
    )


def upload_file_to_s3(
    s3_client, local_file_path: str, s3_path: str, force_overwrite: bool = False
) -> None:
    """Uploads a local file to an S3 bucket and verifies the upload.

    Args:
        s3_client: The boto3 S3 client.
        local_file_path (str): The path to the local file to upload.
        s3_path (str): The destination S3 path.
        force_overwrite (bool): Whether to overwrite the file on S3 if it already exists.
    """
    bucket, key = parse_s3_path(s3_path)
    if not force_overwrite and s3_file_exists(s3_client, bucket, key):
        log.warning(f"The file s3://{bucket}/{key} already exists. Skipping upload.")
        return

    try:
        # Calculate the MD5 checksum of the local file
        local_md5 = calculate_md5(local_file_path)
        log.info(f"MD5 checksum of local file {local_file_path}: {local_md5}")

        # Upload the file to S3
        log.info(f"Uploading {local_file_path} to s3://{bucket}/{key}")
        s3_client.upload_file(local_file_path, bucket, key)
        log.info(f"Successfully uploaded {local_file_path} to s3://{bucket}/{key}")

        # Verify the upload by comparing MD5 checksums
        s3_md5 = calculate_md5(s3_path, s3_client=s3_client)
        log.info(f"MD5 checksum of uploaded file s3://{bucket}/{key}: {s3_md5}")

        if local_md5 == s3_md5:
            log.info(f"File {local_file_path} successfully verified after upload.")
        else:
            log.error(
                f"MD5 checksum mismatch: local file {local_md5} != s3 file {s3_md5}"
            )
            raise ValueError("MD5 checksum mismatch after upload.")

    except FileNotFoundError:
        log.error(f"The file {local_file_path} was not found.")
    except s3_client.exceptions.NoCredentialsError:
        log.error("Credentials not available.")
    except s3_client.exceptions.PartialCredentialsError:
        log.error("Incomplete credentials provided.")
    except Exception as e:
        log.error(f"An error occurred: {e}")


def s3_file_exists(s3_client, bucket_or_path: str, key: str = None) -> bool:
    """
    Check if a file exists in an S3 bucket.

    Args:
        s3_client: The boto3 S3 client.
        bucket_or_path (str): The name of the S3 bucket or the full S3 path.
        key (str, optional): The key of the file in the S3 bucket.
            Required if bucket_or_path is a bucket name.

    Returns:
        bool: True if the file exists, False otherwise.
    """
    if key is None:
        # Assume bucket_or_path is a full S3 path
        if not bucket_or_path.startswith("s3://"):
            raise ValueError("Invalid S3 path")
        bucket, key = parse_s3_path(bucket_or_path)
    else:
        # Assume bucket_or_path is a bucket name
        bucket = bucket_or_path

    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except s3_client.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        else:
            raise


def get_s3_resource(
    access_key: str | None = None,
    secret_key: str | None = None,
    host_url: str | None = None,
) -> Any:
    """Configures and returns an S3 resource object.

    If the optional access key, secret key, and host URL are not provided, the
    method uses environment variables to configure the S3 resource object. Support
    .env configuration.

    Args:
        access_key (str | None, optional): The access key for S3. Defaults to None.
        secret_key (str | None, optional): The secret key for S3. Defaults to None.
        host_url (str | None, optional): The host URL for S3. Defaults to None.

        Returns:
            Any: The configured S3 resource.
    """

    access_key = access_key or os.getenv("SE_ACCESS_KEY")
    secret_key = secret_key or os.getenv("SE_SECRET_KEY")
    host_url = host_url or os.getenv("SE_HOST_URL")
    return boto3.resource(
        "s3",
        aws_secret_access_key=secret_key,
        aws_access_key_id=access_key,
        endpoint_url=host_url,
    )


def parse_s3_path(s3_path: str) -> Tuple[str, str]:
    """
    Parses an S3 path into a bucket name and prefix.

    Args:
        s3_path (str): The S3 path to parse.

    Returns:
        Tuple[str, str]: The bucket name and prefix.

    Raises:
        ValueError: If the S3 path does not start with "s3://" or if it does not include
        both a bucket name and prefix.

    >>> parse_s3_path("s3://mybucket/myfolder/myfile.txt")
    ('mybucket', 'myfolder/myfile.txt')

    >>> parse_s3_path("s3://mybucket/myfolder/subfolder/")
    ('mybucket', 'myfolder/subfolder/')

    >>> parse_s3_path("not-an-s3-path")
    Traceback (most recent call last):
    ...
    ValueError: S3 path must start with s3://
    """
    if not s3_path.startswith("s3://"):
        raise ValueError("S3 path must start with s3://: %s", s3_path)
    path_parts = s3_path[5:].split("/", 1)
    if len(path_parts) < 2:
        raise ValueError("S3 path must include both bucket name and prefix")
    return path_parts[0], path_parts[1]


class S3Compressor:
    def __init__(
        self,
        s3_path: str,
        local_path: Optional[str] = None,
        new_s3_path: Optional[str] = None,
        new_bucket: Optional[str] = None,
        strip_local_extension: Optional[str] = None,
        s3_client: Optional[boto3.client] = None,
    ):
        self.s3_path = s3_path
        self.local_path = local_path
        self.new_s3_path = new_s3_path
        self.new_bucket = new_bucket
        self.strip_local_extension = strip_local_extension
        self.s3_client = s3_client or get_s3_client()

    def compress_and_upload(self) -> None:
        """
        Downloads an S3 file, compresses it as bz2, uploads it under the same name, and verifies the MD5 checksum.
        """
        if self.new_s3_path:
            compressed_bucket, compressed_key = parse_s3_path(self.new_s3_path)
        else:
            compressed_bucket, compressed_key = parse_s3_path(self.s3_path)

        if self.local_path is None:
            if self.strip_local_extension is not None:
                if self.s3_path.endswith(self.strip_local_extension):
                    self.local_path = self.s3_path[5:][
                        : -len(self.strip_local_extension)
                    ]
                else:
                    log.error(
                        "The s3_path %s does not end with the specified extension: %s",
                        self.s3_path,
                        self.strip_local_extension,
                    )
                    sys.exit(1)
            else:
                self.local_path = self.s3_path[5:]

        if self.new_s3_path is None:
            if self.new_bucket is None:
                self.new_s3_path = self.s3_path
                log.warning(
                    "Overwriting the original file %s. Taking care to not overwrite the"
                    " original file in case of network problems.",
                    self.s3_path,
                )
            else:
                compressed_bucket = self.new_bucket
        else:
            if self.new_bucket is None:
                compressed_bucket, compressed_key = parse_s3_path(self.new_s3_path)
            else:
                log.warning("Specifying s3_path and bucket is invalid")
                sys.exit(2)
        log.warning(
            f"Compressing {self.s3_path} to {compressed_bucket}/{compressed_key}"
        )

        compressed_local_path = self.local_path + ".bz2"

        # Download the file from S3
        result = download_with_retries(self.s3_client, self.s3_path, self.local_path)
        if not result:
            log.error(
                "Failed to download %s after multiple attempts. Aborting compression.",
                self.s3_path,
            )
            return
        log.warning("Downloaded %s to %s", self.s3_path, self.local_path)
        # Check if the file is already compressed
        try:
            with bz2.open(self.local_path, "rb") as test_file:
                test_file.read(1)
            log.warning(
                f"The file {self.local_path} is already compressed. Removing local"
                " file %s",
                self.local_path,
            )
            os.remove(self.local_path)
            return
        except OSError:
            log.warning(
                f"The file {self.local_path} is not compressed. Proceeding with"
                " compression.",
            )

        # Compress the file
        with open(self.local_path, "rb") as input_file:
            with bz2.open(compressed_local_path, "wb") as output_file:
                output_file.write(input_file.read())
            log.warning("Compressed %s to %s", self.local_path, compressed_local_path)

        # Upload the compressed file to S3 (overwriting the existing file)
        result = upload_with_retries(
            self.s3_client, compressed_local_path, self.new_s3_path
        )
        if not result:
            log.error(
                "Failed to upload %s to %s after multiple attempts.",
                compressed_local_path,
                self.new_s3_path,
            )

        # Clean up local files
        os.remove(self.local_path)
        os.remove(compressed_local_path)


class LocalStampCreator(object):
    """Main application for creating local stamp files mirroring S3 objects.

    Attributes:
        args (Any): Command-line arguments object.
        s3_resource (boto3.resources.factory.s3.ServiceResource): The S3 service
            resource.

    Methods:
        run(): Orchestrates the stamp file creation process.

        create_stamp_files(bucket_name: str, prefix: str): Creates local stamp files
            based on S3 objects.

        create_local_stamp_file(s3_key: str, last_modified: datetime.datetime): Creates
            a single local stamp file.
    """

    def __init__(self, args: argparse.Namespace):
        """Initializes the application with command-line arguments.

        Args:
            args: Command-line arguments.
        """

        self.args = args
        self.s3_resource = get_s3_resource()
        self.stats = {"files_created": 0}  # Initialize the statistics dictionary
        # Splitting the s3-path into bucket name and prefix
        self.bucket_name, self.prefix = parse_s3_path(self.args.s3_path)

    def run(self) -> None:
        """Orchestrates the stamp file creation process or uploads a file to S3."""
        if self.args.upload_file:
            if not self.args.s3_path:
                log.error(
                    "When using --upload-file, you must specify the s3_path as the"
                    " destination."
                )
                sys.exit(1)
            upload_file_to_s3(
                get_s3_client(),
                self.args.upload_file,
                self.args.s3_path,
                self.args.force_overwrite,
            )
            sys.exit(0)
        elif self.args.list_files:
            bucket = self.s3_resource.Bucket(self.bucket_name)
            glob = self.args.list_files_glob or None

            for obj in bucket.objects.filter(Prefix=self.prefix):
                if glob:
                    if not fnmatch.fnmatch(obj.key, glob):
                        continue
                print(f"s3://{self.bucket_name}/{obj.key}")
            sys.exit(0)
        elif self.args.s3_path:
            log.info("Starting stamp file creation...")
            self.create_stamp_files(self.bucket_name, self.prefix)
            log.info(
                "Stamp file creation completed. Files created: %d",
                self.stats["files_created"],
            )
        else:
            log.error(
                "No action specified. Provide s3_path for stamp creation or use"
                " --upload-file for uploading."
            )
            sys.exit(1)

    def create_stamp_files(self, bucket_name: str, prefix: str) -> None:
        """Creates local stamp files that mirror the structure of specified S3 objects.

        Args:
            bucket_name (str): The name of the S3 bucket.
            prefix (str): The file prefix to match in the S3 bucket.
        """
        bucket = self.s3_resource.Bucket(bucket_name)
        for s3_object in bucket.objects.filter(Prefix=prefix):

            s3_key = s3_object.key
            last_modified = s3_object.last_modified

            # Skip directories and zero-size objects
            if s3_key.endswith("/"):
                local_dir = os.path.join(self.args.local_dir, s3_key)
                if not os.path.exists(local_dir):
                    os.makedirs(local_dir)
                    logging.info("Created local directory: '%s'", local_dir)
                continue
            # Get the content of the S3 object
            content = (
                self.get_s3_object_content(s3_key) if self.args.write_content else None
            )

            # Create a local stamp file
            self.create_local_stamp_file(s3_key, last_modified, content)

    def get_s3_object_content(self, s3_key: str) -> str:
        """Get the content of an S3 object.

        Args:
            s3_key (str): The key of the S3 object.

        Returns:
            str: The content of the S3 object.
        """

        obj = self.s3_resource.Object(self.bucket_name, s3_key)
        raw_content = obj.get()["Body"].read()
        content = raw_content
        # Decompress the content
        if s3_key.endswith(".bz2"):
            content = bz2.decompress(raw_content)

        return content.decode("utf-8")

    def create_local_stamp_file(
        self,
        s3_key: str,
        last_modified: datetime.datetime,
        content: Optional[str] = None,
    ) -> None:
        """Creates a local stamp file, mirroring the modification date of an S3 object.

        Args:
            s3_key (str): The key of the S3 object.

            last_modified (datetime.datetime): The last-modified timestamp of the S3
                 object.
        """

        local_file_path = s3_key.replace("/", os.sep)
        # include  bucket name in local file path depending on the --no-bucket flag
        if not self.args.no_bucket:
            local_file_path = os.path.join(self.bucket_name, local_file_path)

        # Adjust the file path to include the local directory
        local_file_path = os.path.join(self.args.local_dir, local_file_path)
        if content is None:
            local_file_path += self.args.stamp_extension

        os.makedirs(os.path.dirname(local_file_path), exist_ok=True)

        with smart_open.open(local_file_path, "w", encoding="utf-8") as f:
            f.write(content if content is not None else "")

        os.utime(
            local_file_path, (last_modified.timestamp(), last_modified.timestamp())
        )

        self.stats["files_created"] += 1
        log.info(f"'{local_file_path}' created. Last modification: {last_modified}")


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="S3 to Local Stamp File Creator",
        epilog="Utility to mirror S3 file structure locally with stamp files.",
    )

    parser.add_argument(
        "s3_path",
        help=(
            "S3 path prefix in the format s3://BUCKET_NAME/PREFIX. "
            "The prefix is used to match objects in the specified bucket."
        ),
    )
    parser.add_argument(
        "--upload-file",
        help="Path to the local file to upload to S3.",
        metavar="LOCAL_FILE",
    )
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="Overwrite the --upload-file on S3 even if it already exists.",
    )
    parser.add_argument(
        "--level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level. Default: %(default)s",
    )
    parser.add_argument("--logfile", help="Write log to FILE", metavar="FILE")

    parser.add_argument(
        "--local-dir",
        default="./",
        type=str,
        help="Local directory prefix for creating stamp files %(default)s",
    )
    parser.add_argument(
        "--no-bucket",
        help="Do not use bucket name for local files, only the key. %(default)s",
        action="store_true",
    )
    parser.add_argument(
        "--stamp-extension",
        help=(
            "Append this extension to all file names created (preceding dot must be"
            " specified). %(default)s"
        ),
        default=".stamp",
    )
    parser.add_argument(
        "--write-content",
        action="store_true",
        help=(
            "Write the content of the S3 objects to the local stamp files. Not used for"
            " upload!"
        ),
    )
    parser.add_argument(
        "--list-files",
        action="store_true",
        help=(
            "list all files in the bucket and prefix on stdout and exit. No stamp files"
            " are created."
        ),
    )
    parser.add_argument(
        "--list-files-glob",
        help=(
            "Specify a file glob filter on the keys. Only used"
            " with option --list-files."
        ),
    )
    arguments = parser.parse_args()

    to_logging_level = {
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
    }
    logging.basicConfig(
        level=to_logging_level[arguments.level],
        format="%(asctime)-15s %(filename)s:%(lineno)d %(levelname)s: %(message)s",
        force=True,
    )
    log.info("Arguments: %s", arguments)
    try:
        processor = LocalStampCreator(arguments)
        processor.run()
    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        log.error("Traceback: %s", traceback.format_exc())
        sys.exit(1)
