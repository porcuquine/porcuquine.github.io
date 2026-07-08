EMACS ?= $(shell if [ -x /opt/homebrew/opt/emacs/bin/emacs ]; then echo /opt/homebrew/opt/emacs/bin/emacs; elif [ -x /opt/homebrew/bin/emacs ]; then echo /opt/homebrew/bin/emacs; else echo emacs; fi)
SRC_DIR ?= src
OUTPUT_DIR ?= public
ZIP_DIR ?= zips
ZIP_FILE ?= porcuquine-site-$(shell date +%F).zip
ZIP_PATH ?= $(abspath $(ZIP_DIR)/$(ZIP_FILE))

ORG_FILES := \
	prompting-as-essay.org \
	committee.org \
	the-gradient.org \
	mirrors-are-also-people.org \
	the-boring-day.org
ORG_TARGETS := $(addprefix $(OUTPUT_DIR)/,$(ORG_FILES:.org=.html))
STATIC_HTML := \
	index.html \
	an-essay-written-with-a-language-model.html \
	market-forces-and-reality.html \
	in-context-learning-exploration.html \
	committee-behind-the-scenes.html \
	the-gradient-behind-the-scenes.html \
	mirrors-are-also-people-behind-the-scenes.html \
	the-boring-day-behind-the-scenes.html
STATIC_TARGETS := $(addprefix $(OUTPUT_DIR)/,$(STATIC_HTML))

.PHONY: all clean zip latest-zip add-chatgpt-piece add-codex-piece

all: $(ORG_TARGETS) $(STATIC_TARGETS)

$(OUTPUT_DIR):
	mkdir -p "$(OUTPUT_DIR)"

$(ZIP_DIR):
	mkdir -p "$(ZIP_DIR)"

clean:
	rm -rf "$(OUTPUT_DIR)"

zip latest-zip: all | $(ZIP_DIR)
	rm -f "$(ZIP_PATH)"
	cd "$(OUTPUT_DIR)" && zip -r "$(ZIP_PATH)" .
	@echo "Wrote $(ZIP_PATH)"

add-chatgpt-piece:
	test -n "$(URL)"
	SRC_DIR="$(SRC_DIR)" python3 build/add-chatgpt-piece.py "$(URL)"

add-codex-piece:
	test -n "$(TRANSCRIPT)"
	test -n "$(TITLE)"
	test -n "$(SLUG)"
	SRC_DIR="$(SRC_DIR)" python3 build/add-codex-piece.py "$(TRANSCRIPT)" --title "$(TITLE)" --slug "$(SLUG)"

$(OUTPUT_DIR)/%.html: $(SRC_DIR)/%.org build/export-org.el | $(OUTPUT_DIR)
	OUTPUT_DIR="$(OUTPUT_DIR)" $(EMACS) --batch -Q -l build/export-org.el "$<"

$(OUTPUT_DIR)/%.html: $(SRC_DIR)/%.html | $(OUTPUT_DIR)
	cp "$<" "$@"
