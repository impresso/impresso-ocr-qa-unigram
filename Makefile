
#### ENABLE LOGGING FIRST
#### OVERWRITE THE LOGGING LEVEL VARIABLE IN THE .env FILE or config.local.mk
LOGGING_LEVEL ?= INFO

# Load our make logging functions
include cookbook/log.mk

# USER-VARIABLE: CONFIG_LOCAL_MAKE
# Defines the name of the local configuration file to include.
#
# This file is used to override default settings and provide local configuration. If a
# file with this name exists in the current directory, it will be included. If the file
# does not exist, it will be silently ignored. Never add the file called config.local.mk
# to the repository! If you have stored config files in the repository set the
# CONFIG_LOCAL_MAKE variable to a different name.
CONFIG_LOCAL_MAKE ?= config.local.mk

# Load local config if it exists (ignore silently if it does not exists)
-include $(CONFIG_LOCAL_MAKE)


# Now we can use the logging functions
  $(call log.info, LOGGING_LEVEL)

# BASIC CONFIGURATION AND SETTINGS FOR THE MAKE PROGRAM
include cookbook/make_settings.mk

# OVERWRITE THE SHELL VARIABLE here if you need to use a different shell than /bin/dash
# SHELL := /bin/bash

###
# SETTINGS FOR THE BUILD PROCESS


# Set the number of parallel launches of newspapers (uses xargs)
# Note: For efficient parallelization the number of cores should be PARALLEL_NEWSPAPERS * MAKE_PARALLEL_PROCESSING_NEWSPAPER_YEAR
#PARALLEL_NEWSPAPERS ?= 1
#  $(call log.debug, PARALLEL_NEWSPAPERS)

# Set the number of parallel jobs of newspaper-year files to process
#  $(call log.debug, MAKE_PARALLEL_PROCESSING_NEWSPAPER_YEAR)
#MAKE_PARALLEL_PROCESSING_NEWSPAPER_YEAR ?= 1 


# Get the current git version
ifndef git_version
git_version := $(shell git describe --tags --always)
endif
  $(call log.info, git_version)
export git_version

###
# SETTING DEFAULT VARIABLES FOR THE PROCESSING

# The build directory where all local input and output files are stored
# The content of BUILD_DIR can be removed anytime without issues regarding s3
BUILD_DIR ?= build.d
  $(call log.debug, BUILD_DIR)

# Specify the newspaper to process. Just a suffix appended to the s3 bucket name
# is ok! Can also be something like actionfem/actionfem-1933 to restrict further
NEWSPAPER ?= actionfem
  $(call log.info, NEWSPAPER)

# Help: Show this help message
help::
	@echo "Usage: make <target>"
	@echo "Targets:"
	@echo "  setup                 # Prepare the local directories"
	@echo "  collection            # Call make all for each newspaper found in the file $(NEWSPAPERS_TO_PROCESS_FILE)"
	@echo "  all                   # Resync the data from the S3 bucket to the local directory and process all years of a single newspaper"
	@echo "  newspaper             # Process a single newspaper for all years"
	@echo "  sync                  # Sync the data from the S3 bucket to the local directory"
	@echo "  resync                # Remove the local synchronization file stamp and sync again."
	@echo "  clean-build           # Remove the entire build directory"
	@echo "  clean-newspaper       # Remove the local directory for a single newspaper"
	@echo "  update-requirements   # Update the requirements.txt file with the current pipenv requirements."
	@echo "  help                  # Show this help message"

.DEFAULT_GOAL := help
PHONY_TARGETS += help

###
# INCLUDES AND CONFIGURATION FILES
#------------------------------------------------------------------------------
# Load general setup
include cookbook/setup.mk
include cookbook/setup_python.mk
include cookbook/setup_ocrqa.mk
# Load newspaper list configuration and processing rules
include cookbook/newspaper_list.mk

# Load input path definitions for rebuilt content
include cookbook/paths_rebuilt.mk

# Load input path definitions for language identification
include cookbook/paths_langident.mk

# Load output path definitions for ocr quality assessment
include cookbook/paths_ocrqa.mk



# Load setup rules for ocr quality assessment
#include cookbook/setup_ocrqa.mk

###
# MAIN TARGETS
#------------------------------------------------------------------------------

include cookbook/main_targets.mk

###
# SYNCHRONIZATION TARGETS
#------------------------------------------------------------------------------

include cookbook/sync.mk

# Include synchronization rules for rebuilt content
include cookbook/sync_rebuilt.mk

# Include synchronization rules for langident content
include cookbook/sync_langident.mk

# Include synchronization rules for ocr quality assessment
include cookbook/sync_ocrqa.mk

# Include cleanup rules
include cookbook/clean.mk


###
# PROCESSING TARGETS
#------------------------------------------------------------------------------
include cookbook/processing.mk

# Include main ocr quality assessment processing rules
include cookbook/processing_ocrqa.mk



###
# FINAL DECLARATIONS AND UTILITIES
#------------------------------------------------------------------------------

# Declare all targets that don't produce files
.PHONY: $(PHONY_TARGETS)

# Include path conversion utilities
include cookbook/local_to_s3.mk
