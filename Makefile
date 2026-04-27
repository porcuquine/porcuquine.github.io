EMACS ?= $(shell if [ -x /opt/homebrew/bin/emacs ]; then echo /opt/homebrew/bin/emacs; else echo emacs; fi)
OUTPUT_DIR ?= public

ORG_FILES := $(wildcard *.org)
ORG_TARGETS := $(addprefix $(OUTPUT_DIR)/,$(ORG_FILES:.org=.html))
STATIC_HTML := $(filter-out $(ORG_FILES:.org=.html),$(wildcard *.html))
STATIC_TARGETS := $(addprefix $(OUTPUT_DIR)/,$(STATIC_HTML))

.PHONY: all clean

all: $(ORG_TARGETS) $(STATIC_TARGETS)

$(OUTPUT_DIR):
	mkdir -p "$(OUTPUT_DIR)"

clean:
	rm -rf "$(OUTPUT_DIR)"

$(OUTPUT_DIR)/%.html: %.org build/export-org.el | $(OUTPUT_DIR)
	OUTPUT_DIR="$(OUTPUT_DIR)" $(EMACS) --batch -Q -l build/export-org.el "$<"

$(OUTPUT_DIR)/%.html: %.html | $(OUTPUT_DIR)
	cp "$<" "$@"
