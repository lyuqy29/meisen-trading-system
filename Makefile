SHELL := /bin/bash
PY ?= python3
SKILL_DIR ?= $(HOME)/.dsh/skills/meisen-trading-system

.PHONY: help test check index sectors stock install uninstall clean git-status

help:
	@echo "make test      离线结构校验（CI 同款）"
	@echo "make index     大盘三大指数状态"
	@echo "make sectors   板块持续性排名"
	@echo "make stock C=601985,688172   个股状态"
	@echo "make check     盘中触发器检查"
	@echo "make install   安装到 $(SKILL_DIR)"
	@echo "make uninstall 卸载"

test:
	$(PY) tests/test_skill.py
	$(PY) tests/test_ms_engine.py

index:
	$(PY) scripts/ms_data.py index

sectors:
	$(PY) scripts/ms_data.py sectors

stock:
	$(PY) scripts/ms_data.py stock $(C)

check:
	$(PY) scripts/ms_check.py

install:
	bash install-skill.sh --force

uninstall:
	bash install-skill.sh --uninstall

git-status:
	$(PY) scripts/git.py status

clean:
	rm -rf __pycache__ scripts/__pycache__ tests/__pycache__ .pytest_cache
