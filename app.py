# -*- coding: utf-8 -*-
"""Compatibility launcher.

The former monolithic prototype has been replaced by the modular Recruitment
Workbench V1. Keep this file so existing shortcuts and build scripts continue to work.
"""
from workbench_app import main


if __name__ == "__main__":
    raise SystemExit(main())
