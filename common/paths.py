"""[AppChef 路径集中配置] 避免硬编码盘符，数据库与日志统一落在包内 resources。"""
from pathlib import Path

# appchef 包根目录（含 agents、api 等）
APPCHEF_ROOT = Path(__file__).resolve().parent.parent
RESOURCES_DIR = APPCHEF_ROOT / "resources"
LOGS_DIR = RESOURCES_DIR / "logs"

RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

CHECKPOINT_DB = RESOURCES_DIR / "personal_chief.db"
MEMORY_DB = RESOURCES_DIR / "appchef_memory.db"
