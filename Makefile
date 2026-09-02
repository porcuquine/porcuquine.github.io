EMACS ?= $(shell if [ -x /opt/homebrew/opt/emacs/bin/emacs ]; then echo /opt/homebrew/opt/emacs/bin/emacs; elif [ -x /opt/homebrew/bin/emacs ]; then echo /opt/homebrew/bin/emacs; else echo emacs; fi)
SRC_DIR ?= src
ESSAY_DIR ?= $(SRC_DIR)/essays
STATIC_DIR ?= $(SRC_DIR)/static
BEHIND_DIR ?= $(SRC_DIR)/behind-the-scenes
TRANSCRIPT_DIR ?= $(SRC_DIR)/transcripts
INDEX_PATH ?= $(STATIC_DIR)/index.html
OUTPUT_DIR ?= public
ZIP_DIR ?= zips
ZIP_FILE ?= porcuquine-site-$(shell date +%F).zip
ZIP_PATH ?= $(abspath $(ZIP_DIR)/$(ZIP_FILE))
ADD_CHATGPT_ARGS := $(foreach block,$(LITERAL_WRITING_MATH),--literal-writing-math $(block))
ADD_CHATGPT_ARGS += $(if $(SUBTITLE),--subtitle "$(SUBTITLE)")

ORG_FILES := \
	prompting-as-essay.org \
	committee.org \
	the-gradient.org \
	mirrors-are-also-people.org \
	the-boring-day.org \
	the-impostor-alarm.org \
	the-batch.org
ORG_TARGETS := $(addprefix $(OUTPUT_DIR)/,$(ORG_FILES:.org=.html))
STATIC_HTML := \
	index.html \
	an-essay-written-with-a-language-model.html \
	market-forces-and-reality.html \
	in-context-learning-exploration.html
BEHIND_SCENES_HTML := \
	committee-behind-the-scenes.html \
	the-gradient-behind-the-scenes.html \
	mirrors-are-also-people-behind-the-scenes.html \
	the-boring-day-behind-the-scenes.html \
	the-impostor-alarm-behind-the-scenes.html \
	the-batch-behind-the-scenes.html
STATIC_TARGETS := $(addprefix $(OUTPUT_DIR)/,$(STATIC_HTML))
BEHIND_SCENES_TARGETS := $(addprefix $(OUTPUT_DIR)/,$(BEHIND_SCENES_HTML))

.PHONY: all clean zip latest-zip add-chatgpt-piece add-codex-piece

all: $(ORG_TARGETS) $(STATIC_TARGETS) $(BEHIND_SCENES_TARGETS)

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
	SRC_DIR="$(SRC_DIR)" ESSAY_DIR="$(ESSAY_DIR)" BEHIND_DIR="$(BEHIND_DIR)" INDEX_PATH="$(INDEX_PATH)" python3 build/add-chatgpt-piece.py "$(URL)" $(ADD_CHATGPT_ARGS)

add-codex-piece:
	test -n "$(TRANSCRIPT)"
	test -n "$(TITLE)"
	test -n "$(SLUG)"
	SRC_DIR="$(SRC_DIR)" ESSAY_DIR="$(ESSAY_DIR)" BEHIND_DIR="$(BEHIND_DIR)" INDEX_PATH="$(INDEX_PATH)" python3 build/add-codex-piece.py "$(TRANSCRIPT)" --title "$(TITLE)" --slug "$(SLUG)"

$(OUTPUT_DIR)/%.html: $(ESSAY_DIR)/%.org build/export-org.el | $(OUTPUT_DIR)
	OUTPUT_DIR="$(OUTPUT_DIR)" $(EMACS) --batch -Q -l build/export-org.el "$<"

$(OUTPUT_DIR)/%-behind-the-scenes.html: $(BEHIND_DIR)/%-behind-the-scenes.html | $(OUTPUT_DIR)
	cp "$<" "$@"

$(OUTPUT_DIR)/%.html: $(STATIC_DIR)/%.html | $(OUTPUT_DIR)
	cp "$<" "$@"
