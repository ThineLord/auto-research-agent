.DEFAULT_GOAL := help
# Explicit phony goals: a pattern rule treats an existing same-named directory
# as up to date and skips forwarding.
.PHONY: help $(MAKECMDGOALS)

help:
	@$(MAKE) --no-print-directory -C app help

ifneq ($(filter-out help,$(MAKECMDGOALS)),)
$(filter-out help,$(MAKECMDGOALS)):
	@$(MAKE) --no-print-directory -C app $@
endif
