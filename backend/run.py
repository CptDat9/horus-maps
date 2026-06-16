"""Run application with Uvicorn"""
import uvicorn
from app.main import app
from app.configs.config import Config

if __name__ == "__main__":
    config = Config()
    uvicorn.run(
        "app.main:app",
        host=config.RUN_SETTING.get("host", "0.0.0.0"),
        port=config.RUN_SETTING.get("port", 8000),
        reload=config.RUN_SETTING.get("auto_reload", True),
        log_level="info",
    )
