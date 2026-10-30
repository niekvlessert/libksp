#!/usr/bin/env python3
# Compatibility entry point. The shared converter auto-detects S3M/XM/MOD.
from tracker2ksp import main
if __name__ == '__main__':
    raise SystemExit(main())
