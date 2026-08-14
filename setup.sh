#!/bin/bash
# Unix 便捷入口: 实际逻辑在跨平台 setup.py (Windows 直接运行 python setup.py)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/setup.py" "$@"
