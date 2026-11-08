.DEFAULT_GOAL := help
.PHONY: help
help:
	@$(MAKE) --no-print-directory -C app help
%:
	@$(MAKE) --no-print-directory -C app $@
